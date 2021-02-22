#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
# adapted from https://github.com/cowlicks/badger-claw

import argparse
import contextlib
import copy
import glob
import json
import logging
import os
import pathlib
import random
import re
import sys
import tempfile
import time

from datetime import datetime, timedelta
from pprint import pformat
from shutil import copytree
from urllib3.exceptions import ProtocolError
from urllib.parse import urljoin, urlparse

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    InvalidSessionIdException,
    NoAlertPresentException,
    NoSuchElementException,
    NoSuchWindowException,
    SessionNotCreatedException,
    StaleElementReferenceException,
    TimeoutException,
    UnexpectedAlertPresentException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from tldextract import TLDExtract
from tranco import Tranco
from xvfbwrapper import Xvfb


CHROME_EXT_ID = 'mcgekeccgjgcmhnhbabplanchdogjcnh'
CHROME_URL_FMT = 'chrome-extension://%s/'
CHROMEDRIVER_PATH = 'chromedriver'
FF_URL_FMT = 'moz-extension://%s/'
FF_EXT_ID = 'jid1-MnnxcxisBPnSXQ@jetpack'
FF_UUID = 'd56a5b99-51b6-4e83-ab23-796216679614'
FF_BIN_PATH = '/usr/bin/firefox'
BACKGROUND = '_generated_background_page.html'
OPTIONS = 'skin/options.html'

CHROME = 'chrome'
FIREFOX = 'firefox'

DEFAULT_NUM_SITES = 2000
RESTART_RETRIES = 5
MAX_ALERTS = 10

# day before yesterday, as yesterday's list is sometimes not yet available
TRANCO_VERSION = (datetime.utcnow() - timedelta(days=2)).strftime('%Y-%m-%d')


ap = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)

ap.add_argument('--browser', choices=[FIREFOX, CHROME], default=CHROME,
                help='Browser to use for the scan')
ap.add_argument('--n-sites', type=int, default=DEFAULT_NUM_SITES,
                help='Number of websites to visit on the crawl')
ap.add_argument('--exclude', default=None,
                help='Exclude a TLD or comma-separated TLDs from the scan')
ap.add_argument('--timeout', type=float, default=30.0,
                help='Amount of time to allow each site to load, in seconds')
ap.add_argument('--wait-time', type=float, default=5.0, help=(
    "Amount of time to wait on each site after it loads, in seconds"
))
ap.add_argument('--log-stdout', action='store_true', default=False,
                help='If set, log to stdout as well as log.txt')
ap.add_argument('--load-extension', default=None,
                help='If set, load arbitrary extension to run in parallel to PB')

ap.add_argument('--load-data', metavar='BADGER_DATA_JSON', action='append', default=[],
                help="If set, load tracker data from specified Badger data JSON file(s)")

ap.add_argument('--survey', action='store_true', default=False,
                help="If set, don't block anything or store action_map data")
ap.add_argument('--domain-list', default=None,
                help="If set, load domains from this file instead of the Tranco list")
ap.add_argument('--max-data-size', type=int, default=2e6,
                help='Maximum size of serialized localstorage data (survey mode only)')

# Arguments below should never have to be used within the docker container.
ap.add_argument('--out-path', default='./',
                help='Path at which to save output')
ap.add_argument('--pb-path', default='./privacybadger',
                help='Path to the Privacy Badger source checkout')
ap.add_argument('--chromedriver-path', default=CHROMEDRIVER_PATH,
                help='Path to the chromedriver binary')
ap.add_argument('--firefox-path', default=FF_BIN_PATH,
                help='Path to the firefox browser binary')

ap.add_argument('--firefox-tracking-protection',
    choices=("off", "standard", "strict"), default="off",
    help="Re-enable or set to strict Enhanced Tracking Protection in Firefox")

ap.add_argument('--no-xvfb', action='store_true', default=False,
                help="Set to disable the virtual display")


# Force a 'Failed to decode response from marionette' crash.
# Example from https://bugzilla.mozilla.org/show_bug.cgi?id=1401131
def test_crash(driver):
    driver.set_context("chrome")
    driver.execute_script("""
// Copied from crash me simple
Components.utils.import("resource://gre/modules/ctypes.jsm");

// ctypes checks for NULL pointer derefs, so just go near-NULL.
var zero = new ctypes.intptr_t(8);
var badptr = ctypes.cast(zero, ctypes.PointerType(ctypes.int32_t));
var crash = badptr.contents;""")


def size_of(data):
    """Get the size (in bytes) of the serialized data structure"""
    return len(json.dumps(data))


# determine whether we need to restart the webdriver after an error
def should_restart(e):
    return (
        isinstance(e, (NoSuchWindowException, SessionNotCreatedException)) or
        "response from marionette" in e.msg or
        "unknown error: failed to close window in 20 seconds" in e.msg or
        "unknown error: session deleted because of page crash" in e.msg or
        e.msg == "TypeError: this.curBrowser.contentBrowser is null"
    )


def wait_for_script(driver, script, timeout=30, message=(
        "Timed out waiting for execute_script to eval to True")):
    return webdriver.support.ui.WebDriverWait(driver, timeout).until(
        lambda driver: driver.execute_script(script), message)


def dismiss_alert(driver):
    try:
        driver.switch_to.alert().dismiss()
    except NoAlertPresentException:
        pass


class Crawler:
    def __init__(self, args):
        assert args.browser in (CHROME, FIREFOX)

        self.browser = args.browser
        self.n_sites = args.n_sites
        self.exclude = args.exclude
        self.timeout = args.timeout
        self.wait_time = args.wait_time
        self.out_path = args.out_path
        self.pb_path = args.pb_path
        self.domain_list = args.domain_list
        self.chromedriver_path = args.chromedriver_path
        self.firefox_path = args.firefox_path
        self.firefox_tracking_protection = args.firefox_tracking_protection
        self.load_extension = args.load_extension

        # version is based on when the crawl started
        self.version = time.strftime('%Y.%-m.%-d', time.localtime())

        # set up logging
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)
        log_fmt = logging.Formatter('%(asctime)s %(message)s')

        # by default, just log to file
        fh = logging.FileHandler(os.path.join(self.out_path, 'log.txt'))
        fh.setFormatter(log_fmt)
        self.logger.addHandler(fh)

        # log to stdout as well if configured
        if args.log_stdout:
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(log_fmt)
            self.logger.addHandler(sh)

        self.last_data = None
        self.storage_objects = ['snitch_map', 'action_map']

        self.tld_extract = TLDExtract(cache_file=False)

        self.start_browser()

        # collect Privacy Badger git info for logging
        def get_git_info(path):
            git_info = {
                'branch': None,
                'commit_hash': None
            }

            git_dir = pathlib.Path(path) / '.git'

            try:
                with (git_dir / 'HEAD').open('r') as head:
                    ref = head.readline().split(' ')[-1].strip()
                    git_info['branch'] = ref.split('/')[2]

                with (git_dir / ref).open('r') as git_hash:
                    git_info['commit_hash'] = git_hash.readline().strip()

            except FileNotFoundError as err:
                self.logger.warning(
                    "Unable to retrieve git repository info "
                    "for Privacy Badger:\n"
                    "%s", err)

            except IndexError:
                # TODO better handle when Privacy Badger is not on a branch
                git_info['branch'] = None
                git_info['commit_hash'] = '???'

            return git_info

        git_data = get_git_info(self.pb_path)

        self.logger.info(
            (
                "Starting new crawl:\n\n"
                "  Badger branch: %s\n"
                "  Badger hash: %s\n"
                "  timeout: %ss\n"
                "  wait time: %ss\n"
                "  survey mode: %s\n"
                "  domain list: %s\n"
                "  domains to crawl: %d\n"
                "  TLDs to exclude: %s\n"
                "  parallel extension: %s\n"
                "  Firefox ETP: %s\n"
                "  driver capabilities:\n\n%s\n"
            ),
            git_data['branch'],
            git_data['commit_hash'],
            self.timeout,
            self.wait_time,
            args.survey,
            self.domain_list if self.domain_list else "Tranco " + TRANCO_VERSION,
            self.n_sites,
            self.exclude,
            self.load_extension,
            self.firefox_tracking_protection,
            pformat(self.driver.capabilities)
        )

        # load tracker data from one or more Badger data JSON files
        for data_json in args.load_data:
            with open(data_json, "r") as f:
                data = json.load(f)
                self.load_user_data(data)

    def handle_alerts_and(self, fun):
        num_tries = 0

        while True:
            num_tries += 1
            try:
                res = fun()
                break
            except UnexpectedAlertPresentException:
                if num_tries > MAX_ALERTS:
                    raise WebDriverException("Too many alerts")
                dismiss_alert(self.driver)

        return res

    def start_driver(self):
        """Start a new Selenium web driver and install the bundled
        extension."""
        if self.browser == CHROME:
            # make extension ID constant across runs

            # create temp directory
            self.tmp_dir = tempfile.TemporaryDirectory()
            new_extension_path = os.path.join(self.tmp_dir.name, "src")

            # copy extension sources there
            copytree(os.path.join(self.pb_path, 'src'), new_extension_path)

            # update manifest.json
            manifest_path = os.path.join(new_extension_path, "manifest.json")
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            # this key and the extension ID
            # must both be derived from the same private key
            manifest['key'] = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArMdgFkGsm7nOBr/9qkx8XEcmYSu1VkIXXK94oXLz1VKGB0o2MN+mXL/Dsllgkh61LZgK/gVuFFk89e/d6Vlsp9IpKLANuHgyS98FKx1+3sUoMujue+hyxulEGxXXJKXhk0kGxWdE0IDOamFYpF7Yk0K8Myd/JW1U2XOoOqJRZ7HR6is1W6iO/4IIL2/j3MUioVqu5ClT78+fE/Fn9b/DfzdX7RxMNza9UTiY+JCtkRTmm4ci4wtU1lxHuVmWiaS45xLbHphQr3fpemDlyTmaVoE59qG5SZZzvl6rwDah06dH01YGSzUF1ezM2IvY9ee1nMSHEadQRQ2sNduNZWC9gwIDAQAB" # noqa:E501 pylint:disable=line-too-long
            with open(manifest_path, "w") as f:
                json.dump(manifest, f)

            opts = ChromeOptions()
            opts.add_argument("--load-extension=" + new_extension_path)

            # loads parallel extension to run alongside pb
            if self.load_extension:
                opts.add_extension(self.load_extension)

            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--disable-crash-reporter")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--dns-prefetch-disable")
            opts.add_argument("--no-sandbox")

            opts.add_experimental_option("prefs", {
                "profile.block_third_party_cookies": False
            })

            opts.set_capability("acceptInsecureCerts", False);
            opts.set_capability("unhandledPromptBehavior", "ignore");

            for _ in range(5):
                try:
                    self.driver = webdriver.Chrome(self.chromedriver_path, options=opts)
                except ConnectionResetError as e:
                    self.logger.warning((
                        "Chrome WebDriver initialization failed:\n"
                        "%s\n"
                        "Retrying ..."), str(e))
                    time.sleep(2)
                else:
                    break

        elif self.browser == FIREFOX:
            profile = webdriver.FirefoxProfile()
            profile.set_preference('extensions.webextensions.uuids',
                                   '{"%s": "%s"}' % (FF_EXT_ID, FF_UUID))

            profile.set_preference("dom.webdriver.enabled", False)

            if self.firefox_tracking_protection == "off":
                # disable all content blocking/Tracking Protection features
                # https://wiki.mozilla.org/Security/Tracking_protection
                profile.set_preference("privacy.trackingprotection.enabled", False)
                profile.set_preference("privacy.trackingprotection.pbmode.enabled", False)
                profile.set_preference("privacy.trackingprotection.cryptomining.enabled", False)
                profile.set_preference("privacy.trackingprotection.fingerprinting.enabled", False)
                profile.set_preference("privacy.trackingprotection.socialtracking.enabled", False)
                # always allow third-party cookies
                profile.set_preference("network.cookie.cookieBehavior", 0)
            elif self.firefox_tracking_protection == "strict":
                profile.set_preference("browser.contentblocking.category", "strict")

            opts = FirefoxOptions()
            #opts.log.level = "trace"

            opts.set_capability("acceptInsecureCerts", False);
            opts.set_capability("unhandledPromptBehavior", "ignore");

            self.driver = webdriver.Firefox(firefox_profile=profile,
                                            firefox_binary=self.firefox_path,
                                            options=opts,
                                            service_log_path=os.path.devnull)

            # load Privacy Badger
            # Firefox requires absolute paths
            unpacked_addon_path = os.path.abspath(
                os.path.join(self.pb_path, 'src'))
            self.driver.install_addon(unpacked_addon_path, temporary=True)

            # loads parallel extension to run alongside pb
            if self.load_extension:
                parallel_extension_url = os.path.abspath(self.load_extension)
                self.driver.install_addon(parallel_extension_url)

        # apply timeout settings
        self.driver.set_page_load_timeout(self.timeout)
        self.driver.set_script_timeout(self.timeout)

        # wait for Badger to finish initializing
        self.load_extension_page(OPTIONS)
        wait_for_script(self.driver, (
            "return chrome.extension.getBackgroundPage()"
            ".badger.INITIALIZED"
        ))

    def load_extension_page(self, page, tries=3):
        """
        Load a page in the Privacy Badger extension. `page` should either be
        BACKGROUND or OPTIONS.
        """
        if self.browser == CHROME:
            EXT_URL = (CHROME_URL_FMT + page) % CHROME_EXT_ID
        elif self.browser == FIREFOX:
            EXT_URL = (FF_URL_FMT + page) % FF_UUID

        def _load_ext_page():
            self.driver.get(EXT_URL)

            # wait for extension page to be ready
            wait_for_script(self.driver, "return chrome.extension")

        for _ in range(tries):
            try:
                self.handle_alerts_and(_load_ext_page)
                break
            except ProtocolError as e:
                self.logger.warning("Error loading %s:\n%s", page, str(e))
                self.restart_browser()
            except TimeoutException:
                self.logger.warning("Timed out loading %s", page)
                self.timeout_workaround()
            except WebDriverException as err:
                self.logger.warning("Error loading %s:\n%s", page, err.msg)
                if should_restart(err):
                    self.restart_browser()
        else:
            raise WebDriverException("Failed to load " + page)

    def load_user_data(self, data):
        """Load saved user data into Privacy Badger after a restart"""
        self.load_extension_page(OPTIONS)
        for obj in self.storage_objects:
            script = (
                "(function (data) {"
                "data = JSON.parse(data);"
                "let bg = chrome.extension.getBackgroundPage();"
                "bg.badger.storage.%s.merge(data.%s);"
                "}(arguments[0]));"
            ) % (obj, obj)
            self.driver.execute_script(script, json.dumps(data))

        time.sleep(2)   # wait for localstorage to sync

    def dump_data(self):
        """Extract the objects Privacy Badger learned during its training
        run."""
        self.load_extension_page(OPTIONS)

        data = {}
        for obj in self.storage_objects:
            script = (
                "return chrome.extension.getBackgroundPage()."
                "badger.storage.%s.getItemClones()" % obj
            )
            data[obj] = self.driver.execute_script(script)
        return data

    def clear_data(self):
        """Clear the training data Privacy Badger starts with."""
        self.load_extension_page(OPTIONS)
        self.driver.execute_script(
            "chrome.extension.getBackgroundPage()."
            "badger.storage.clearTrackerData();"
        )

    def timeout_workaround(self):
        """
        Selenium has a bug where a tab that raises a timeout exception can't
        recover gracefully. So we kill the tab and make a new one.
        """
        # TODO find actual bug ticket
        # TODO do we still need this workaround?

        # guard against stuff like
        # WebDriverException: Message: unknown error: failed to close window in 20 seconds
        try:
            self.driver.close()  # kill the broken site
        except WebDriverException as e:
            self.logger.warning("Error closing timed out window:\n%s", e.msg)
            if should_restart(e):
                self.restart_browser()
            return

        # guard against implicit session deletion
        # TODO when does this happen?
        # when we time out waiting on chrome.extension? ... when does that happen?
        try:
            if not self.driver.window_handles:
                # TODO we probably never get here
                # TODO because looking up window handles
                # TODO after all have been closed raises InvalidSessionIdException
                self.logger.warning("Closed all windows somehow, restarting ...")
                self.restart_browser()
                return
        except InvalidSessionIdException:
            self.logger.warning("Invalid session, restarting ...")
            self.restart_browser()
            return
        except WebDriverException as e:
            self.logger.warning(
                "Failed to get window handles (%s), restarting ...", e.msg)
            self.restart_browser()
            return

        try:
            self.driver.switch_to.window(self.driver.window_handles[0])
        except WebDriverException as e:
            self.logger.warning(
                "Failed to switch windows (%s), restarting ...", e.msg)
            self.restart_browser()
            return

        # open a new window
        if self.driver.current_url.startswith("moz-extension://"):
            # work around https://bugzilla.mozilla.org/show_bug.cgi?id=1491443
            self.driver.execute_script(
                "delete window.__new_window_created;"
                "chrome.windows.create({}, function () {"
                "  window.__new_window_created = true;"
                "});"
            )
            wait_for_script(self.driver, "return window.__new_window_created")
        else:
            self.driver.execute_script('window.open()')

        self.driver.switch_to.window(self.driver.window_handles[-1])

    def raise_on_security_pages(self):
        """
        Errors out on security check pages.
        If we run into a lot of these, we may have a problem.
        """
        page_title = self.driver.title

        if page_title == "Attention Required! | Cloudflare":
            raise WebDriverException("Reached Cloudflare security page")

        # TODO this seems to be out of date
        if page_title == "You have been blocked":
            if "https://ct.captcha-delivery.com/c.js" in self.driver.page_source:
                raise WebDriverException("Reached DataDome security page")

    def raise_on_chrome_error_pages(self):
        # TODO update for changes in Chrome 85? now Chrome raises in many cases
        """
        Chrome doesn't automatically raise WebDriverExceptions on error pages.
        This makes Chrome behave more like Firefox.
        """
        if self.browser != CHROME:
            return

        # self.driver.current_url has the URL we tried, not the error page URL
        actual_page_url = self.handle_alerts_and(
            lambda: self.driver.execute_script("return document.location.href"))

        if not actual_page_url.startswith("chrome-error://"):
            return

        error_text = self.driver.find_element_by_tag_name("body").text
        error_code = error_text

        # for example: ERR_NAME_NOT_RESOLVED
        matches = re.search('(ERR_.+)', error_text)
        if not matches:
            # for example: HTTP ERROR 404
            # TODO these don't seem to be caught by Firefox
            matches = re.search('(HTTP ERROR \\d+)', error_text)
        if matches:
            error_code = matches.group(1)

        if error_code:
            msg = "Reached error page: " + error_code
        else:
            msg = "Reached unknown error page (basic auth prompt?)"

        raise WebDriverException(msg)

    def gather_internal_links(self):
        links = []
        curl = self.driver.current_url

        # path components we care about when looking for links to click
        wanted_paths = ["news", "article", "articles", "story", "video",
                        "videos", "media", "artikel", "news-story", "noticias",
                        "actualite", "actualites", "nachrichten", "nyheter",
                        "noticia", "haber", "notizie"]
        start_year = datetime.today().year - 2
        wanted_paths = [
            str(year) for year in range(start_year, start_year + 3)
        ] + wanted_paths

        for i, el in enumerate(self.driver.find_elements_by_tag_name('a')):
            # limit to checking 200 links
            if i > 199:
                break

            try:
                href = el.get_property('href')
            except StaleElementReferenceException:
                continue

            if not isinstance(href, str):
                # normalize SVG links (href is an SVGAnimatedString object)
                if "baseVal" in href:
                    href = href['baseVal']
                    if href:
                        href = urljoin(curl, href)
                else:
                    self.logger.warning("Skipping unexpected href: %s", href)
                    continue

            # only keep http(s) links that point somewhere else within the site we are on
            if not href or not href.startswith("http") or not href.startswith(curl) or href.startswith(curl + '#'):
                continue

            hpath = urlparse(href).path
            if hpath == "/":
                continue
            # if there is a file extension, limit to allowed extensions
            ext = os.path.splitext(hpath)[1]
            if ext and ext not in ('.html', '.php', '.htm', '.aspx', '.shtml', '.jsp', '.asp'):
                continue
            # limit to news articles for now
            if not any('/' + x + '/' in hpath and not hpath.endswith('/' + x + '/') for x in wanted_paths):
                continue

            # remove duplicates
            if href in [link[0] for link in links]:
                continue

            links.append((href, el))

            # limit to 30 valid links
            if len(links) > 29:
                break

        return links

    def click_internal_link(self):
        links = self.gather_internal_links()
        if not links:
            return

        # sort by link length (try to prioritize article links)
        links.sort(key=lambda item: (-len(item[0]), item[0]))
        # take top ten
        links = links[:10]

        link_href, link_el = random.choice(links)
        self.logger.info("Clicking on %s", link_href)
        try:
            try:
                link_el.click()
            except (ElementClickInterceptedException, ElementNotInteractableException):
                self.driver.execute_script("arguments[0].click()", link_el)
        except WebDriverException as e:
            self.logger.error(
                "Failed to visit link (%s): %s", type(e).__name__, e.msg)
        else:
            time.sleep(self.wait_time)

    def get_domain(self, domain):
        """
        Visit a domain, then spend `self.wait_time` seconds on the site
        waiting for dynamic loading to complete.
        """

        url = "http://%s/" % domain

        self.handle_alerts_and(lambda: self.driver.get(url))

        self.raise_on_chrome_error_pages()
        self.raise_on_security_pages()

        time.sleep(self.wait_time)

        self.click_internal_link()

        return url

    def get_domain_list(self):
        """Get the top n sites from the Tranco list"""
        domains = []
        n_sites = self.n_sites if self.n_sites else DEFAULT_NUM_SITES

        if self.domain_list:
            # read in domains from file
            with open(self.domain_list) as f:
                for l in f:
                    domain = l.strip()
                    if domain and domain[0] != '#':
                        domains.append(domain)
        else:
            self.logger.info("Fetching Tranco list ...")
            domains = Tranco(cache=False).list(TRANCO_VERSION).top()

        # if the exclude TLD option is passed in, remove those TLDs
        if self.exclude:
            filtered_domains = []
            excluded_tlds = self.exclude.split(",")

            self.logger.info("Fetching TLD definitions ...")

            # check for first occurring domains in list that don't have excluded TLD
            for domain in domains:
                if self.tld_extract(domain).suffix not in excluded_tlds:
                    filtered_domains.append(domain)
                # return list of acceptable domains if it's the correct length
                if len(filtered_domains) == n_sites:
                    return filtered_domains

            return filtered_domains

        # if no exclude option is passed in, just return top n domains from list
        return domains[:n_sites]

    def start_browser(self):
        self.start_driver()

        self.clear_data()

        # enable local learning
        self.load_extension_page(OPTIONS)
        wait_for_script(self.driver, "return window.OPTIONS_INITIALIZED")
        try:
            self.driver.find_element_by_id('local-learning-checkbox').click()
        except NoSuchElementException:
            self.logger.warning("Learning checkbox not found, learning NOT enabled!")

    def restart_browser(self):
        self.logger.info("Restarting browser ...")

        # It's ugly, but this section needs to be ABSOLUTELY crash-proof.
        for _ in range(RESTART_RETRIES):
            try:
                self.driver.quit()
            except: # noqa:E722 pylint:disable=bare-except
                pass

            try:
                del self.driver
            except: # noqa:E722 pylint:disable=bare-except
                pass

            try:
                self.start_browser()
                if self.last_data:
                    self.load_user_data(self.last_data)
                else:
                    self.logger.warning("No data to load on restart!")
                self.logger.info("Successfully restarted")
                break
            except Exception as e:
                self.logger.error("Error restarting browser. Retrying ...")
                if isinstance(e, WebDriverException):
                    self.logger.error('%s: %s', type(e).__name__, e.msg)
                else:
                    self.logger.error('%s: %s', type(e).__name__, e)
        else:
            # If we couldn't restart the browser after all that, just quit.
            self.logger.error("Could not restart browser")
            sys.exit(1)

    def get_snitch_map(self):
        self.load_extension_page(OPTIONS)
        return self.driver.execute_script(
            "return chrome.extension.getBackgroundPage()."
            "badger.storage.snitch_map._store;"
        )

    def log_snitch_map_changes(self, old_snitches):
        try:
            snitches = self.get_snitch_map()
        # TODO have all execute_script calls go through this guard
        except TimeoutException:
            # TODO retrying
            self.logger.warning("Timed out getting snitch_map")
            return old_snitches

        diff = set(snitches) - set(old_snitches)
        if diff:
            self.logger.info("New domains in snitch_map: %s", ', '.join(sorted(diff)))
        return snitches

    def crawl(self):
        """
        Visit the top `n_sites` websites in the Tranco list, in order, in
        a virtual browser with Privacy Badger installed. Afterwards, save the
        action_map and snitch_map that the Badger learned.
        """

        if self.n_sites == 0:
            domains = []
        else:
            domains = self.get_domain_list()

        # list of domains we actually visited
        visited = []

        old_snitches = self.get_snitch_map()

        random.shuffle(domains)

        for i, domain in enumerate(domains):
            try:
                # This script could fail during the data dump (trying to get
                # the options page), the data cleaning, or while trying to load
                # the next domain.
                self.last_data = self.dump_data()

                # try to fix misattribution errors
                if i >= 2:
                    clean_data = self.cleanup(
                        domains[i - 2],
                        domains[i - 1]
                    )
                    if self.last_data != clean_data:
                        self.clear_data()
                        self.load_user_data(clean_data)
                        self.last_data = clean_data

                # load the next domain
                self.logger.info("Visiting %d: %s", i + 1, domain)
                url = self.get_domain(domain)
                visited.append(url)
            except ProtocolError as e:
                self.logger.warning("Error loading %s:\n%s", domain, str(e))
                self.restart_browser()
            except TimeoutException:
                self.logger.warning("Timed out loading %s", domain)
                self.timeout_workaround()
            except WebDriverException as e:
                self.logger.error("%s on %s: %s", type(e).__name__, domain, e.msg)
                if should_restart(e):
                    self.restart_browser()
            finally:
                old_snitches = self.log_snitch_map_changes(old_snitches)

        num_total = len(domains)
        if num_total:
            num_successes = len(visited)
            num_errors = num_total - num_successes
            self.logger.info(
                "Finished scan. Visited %d sites and errored on %d (%.1f%%)",
                num_successes, num_errors, (num_errors / num_total * 100)
            )

        try:
            self.logger.info("Getting data from browser storage ...")
            data = self.dump_data()
        except WebDriverException as e:
            # If we can't load the background page here, just quit :(
            self.logger.error("Could not get Badger storage:\n%s", e.msg)
            sys.exit(1)

        self.driver.quit()

        self.save(data)

    def cleanup(self, d1, d2):
        """
        Remove from snitch map any domains that appear to have been added as a
        result of bugs.
        """
        new_data = copy.deepcopy(self.last_data)
        snitch_map = new_data['snitch_map']
        action_map = new_data['action_map']

        # handle blank domain bug
        if '' in action_map:
            self.logger.info("Deleting blank domain from action map")
            self.logger.info(str(action_map['']))
            del action_map['']

        if '' in snitch_map:
            self.logger.info("Deleting blank domain from snitch map")
            self.logger.info(str(snitch_map['']))
            del snitch_map['']

        d1_base = self.tld_extract(d1).registered_domain

        # handle the domain-attribution bug (Privacy Badger issue #1997).
        # If a domain we visited was recorded as a tracker on the domain we
        # visited immediately after it, it's probably a bug
        if d1_base in snitch_map and d2 in snitch_map[d1_base]:
            self.logger.info(
                "Likely bug: domain %s tracking on %s",
                d1_base,
                d2
            )
            snitch_map[d1_base].remove(d2)

            # if the bug caused d1 to be added to the action map, remove it
            if not snitch_map[d1_base]:
                self.logger.info(
                    "Deleting domain %s from action and snitch maps",
                    d1_base
                )
                if d1 in action_map:
                    del action_map[d1]
                if d1_base in action_map:
                    del action_map[d1_base]
                del snitch_map[d1_base]

            # if the bug caused d1 to be blocked, unblock it
            elif len(snitch_map[d1_base]) == 2:
                if d1 in action_map:
                    self.logger.info(
                        'Downgrading domain %s from "block" to "allow"',
                        d1
                    )
                    action_map[d1]['heuristicAction'] = 'allow'
                if d1_base in action_map:
                    self.logger.info(
                        'Downgrading domain %s from "block" to "allow"',
                        d1_base
                    )
                    action_map[d1_base]['heuristicAction'] = 'allow'

        return new_data

    def save(self, data, name='results.json'):
        data['version'] = self.version

        # remove unnecessary properties to save space
        if 'action_map' in self.storage_objects:
            for domain_data in data['action_map'].values():
                # if DNT compliance wasn't seen
                if 'dnt' in domain_data and not domain_data['dnt']:
                    # no need to store DNT compliance
                    del domain_data['dnt']

                # if we haven't yet checked for DNT compliance
                if 'nextUpdateTime' in domain_data and domain_data['nextUpdateTime'] == 0:
                    # no need to store the earliest next check date
                    del domain_data['nextUpdateTime']

                # user actions are never set
                del domain_data['userAction']

        self.logger.info("Saving seed data version %s ...", self.version)
        # save the snitch_map in a human-readable JSON file
        with open(os.path.join(self.out_path, name), 'w') as f:
            json.dump(
                data, f, indent=2, sort_keys=True, separators=(',', ': '))
        self.logger.info("Saved data to %s", name)


class SurveyCrawler(Crawler):
    def __init__(self, args):
        super(SurveyCrawler, self).__init__(args)

        self.max_data_size = args.max_data_size
        self.storage_objects = ['snitch_map']

    def set_passive_mode(self):
        self.load_extension_page(OPTIONS)
        script = '''
chrome.runtime.sendMessage({
    type: "updateSettings",
    data: { passiveMode: true }
});'''
        self.driver.execute_script(script)

    def start_browser(self):
        self.start_driver()
        # TODO should we clear data here?
        # TODO should we enable local learning?
        # don't block anything, just listen and log
        self.set_passive_mode()

    def merge_saved_data(self):
        paths = glob.glob(os.path.join(self.out_path, 'results-*.json'))
        snitch_map = {}
        for p in paths:
            with open(p) as f:
                sm = json.load(f)['snitch_map']
            for tracker, snitches in sm.items():
                if tracker not in snitch_map:
                    snitch_map[tracker] = snitches
                    continue

                for snitch, data in snitches.items():
                    if snitch == 'length':
                        snitch_map[tracker]['length'] = \
                            int(snitch_map[tracker]['length']) + int(data)
                        continue
                    snitch_map[tracker][snitch] = data

        return {'version': self.version, 'snitch_map': snitch_map}

    def crawl(self):
        """
        Visit the top `n_sites` websites in the Tranco list, in order, in
        a virtual browser with Privacy Badger installed. Afterwards, save the
        snitch_map that the Badger learned.
        """

        domains = self.get_domain_list()

        # list of domains we actually visited
        visited = []
        first_i = 0

        i = None
        for i, domain in enumerate(domains):
            # If we can't load the options page for some reason, treat it like
            # any other error
            try:
                # save the state of privacy badger before we do anything else
                self.last_data = self.dump_data()

                # If the localstorage data is getting too big, dump and restart
                if size_of(self.last_data) > self.max_data_size:
                    self.save(self.last_data, 'results-%d-%d.json' % (first_i, i))
                    first_i = i + 1
                    self.last_data = {}
                    self.restart_browser()

                self.logger.info("Visiting %d: %s", i + 1, domain)
                url = self.get_domain(domain)
                visited.append(url)
            except ProtocolError as e:
                self.logger.warning("Error loading %s:\n%s", domain, str(e))
                self.restart_browser()
            except TimeoutException:
                self.logger.warning("Timed out loading %s", domain)
                self.timeout_workaround()
            except WebDriverException as e:
                self.logger.error("%s on %s: %s", type(e).__name__, domain, e.msg)
                if should_restart(e):
                    self.restart_browser()
            except KeyboardInterrupt:
                self.logger.warning(
                    "Keyboard interrupt. Ending scan after %d sites.", i + 1)
                break

        self.logger.info("Finished scan. Visited %d sites and errored on %d",
                         len(visited), i + 1 - len(visited))
        self.logger.info("Getting data from browser storage ...")

        try:
            data = self.dump_data()
        except WebDriverException as e:
            if self.last_data:
                self.logger.error(
                    "Could not get Badger storage:\n"
                    "%s\nUsing cached data ...", e.msg)
                data = self.last_data
            else:
                self.logger.error("Could not export data:\n%s", e.msg)
                sys.exit(1)

        self.driver.quit()

        self.save(data, 'results-%d-%d.json' % (first_i, i))
        self.save(self.merge_saved_data())


if __name__ == '__main__':
    args = ap.parse_args()

    # create an XVFB virtual display (to avoid opening an actual browser)
    with Xvfb(width=1280, height=720) if not args.no_xvfb else contextlib.suppress():
        if args.survey:
            crawler = SurveyCrawler(args)
        else:
            crawler = Crawler(args)

        crawler.crawl()
