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
import subprocess
import sys
import tempfile
import time

from datetime import datetime, timedelta
from pprint import pformat
from shutil import copytree
from urllib3.exceptions import MaxRetryError, ProtocolError
from urllib.parse import urljoin, urlparse

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    ElementNotVisibleException,
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
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tldextract import TLDExtract
from tranco import Tranco
from xvfbwrapper import Xvfb


CHROME_EXT_ID = 'mcgekeccgjgcmhnhbabplanchdogjcnh'
CHROME_URL_PREFIX = 'chrome-extension://'
CHROMEDRIVER_PATH = 'chromedriver'

FF_EXT_ID = 'jid1-MnnxcxisBPnSXQ@jetpack'
FF_UUID = 'd56a5b99-51b6-4e83-ab23-796216679614'
FF_URL_PREFIX = 'moz-extension://'

CHROME = 'chrome'
FIREFOX = 'firefox'
EDGE = 'edge'

DEFAULT_NUM_SITES = 2000
RESTART_RETRIES = 5
MAX_ALERTS = 10

# day before yesterday, as yesterday's list is sometimes not yet available
TRANCO_VERSION = (datetime.utcnow() - timedelta(days=2)).strftime('%Y-%m-%d')


ap = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)

ap.add_argument('--browser', choices=[FIREFOX, CHROME, EDGE], default=CHROME,
                help='Browser to use for the scan')
ap.add_argument('--num-sites', '--n-sites', type=int, default=DEFAULT_NUM_SITES,
                help='Number of websites to visit on the crawl')
ap.add_argument('--exclude', default=None,
                help='Exclude sites from scan whose domains end with one of the specified comma-separated suffixes')
ap.add_argument('--no-blocking', action='store_true', default=False,
                help="Disables blocking and snitch_map limits in Privacy Badger")
ap.add_argument('--timeout', type=float, default=60.0,
                help='Amount of time to allow each site to load, in seconds')
ap.add_argument('--wait-time', type=float, default=5.0, help=(
    "Amount of time to wait on each site after it loads, in seconds"
))
ap.add_argument('--log-stdout', action='store_true', default=False,
                help='If set, log to stdout as well as log.txt')
ap.add_argument('--take-screenshots', action='store_true', default=False,
                help=f"Saves screenshots to {os.path.join('OUT_DIR', 'screenshots')}")
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
ap.add_argument('--out-dir', '--out-path', dest='out_dir', default='./',
                help='Path at which to save output')
ap.add_argument('--pb-dir', '--pb-path', dest='pb_dir', default='./privacybadger',
                help='Path to the Privacy Badger source checkout')
ap.add_argument('--browser-binary', default=None,
                help="Path to the browser binary, for example /usr/bin/google-chrome-beta")
ap.add_argument('--chromedriver-path', default=CHROMEDRIVER_PATH,
                help="Path to the ChromeDriver binary")

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
    ERROR_STRINGS = (
        "chrome not reachable",
        "response from marionette",
        "tab crashed",
        "TypeError: this.curBrowser.contentBrowser is null",
        "unknown error: failed to close window in 20 seconds",
        "unknown error: session deleted because of page crash",
    )
    EXCEPTION_TYPES = (
        InvalidSessionIdException,
        NoSuchWindowException,
        SessionNotCreatedException,
    )

    if isinstance(e, EXCEPTION_TYPES):
        return True

    if any(txt in e.msg for txt in ERROR_STRINGS):
        return True

    return False


def wait_for_script(driver, script, *script_args, execute_async=False, timeout=30,
                    message="Timed out waiting for execute_script to eval to True"):
    def execute_script(dr):
        if execute_async: return dr.execute_async_script(script, *script_args)
        return dr.execute_script(script, *script_args)
    return WebDriverWait(driver, timeout).until(execute_script, message)


def dismiss_alert(driver, accept=False):
    try:
        alert = driver.switch_to.alert
        if accept:
            alert.accept()
        else:
            alert.dismiss()
    except NoAlertPresentException:
        pass


def internal_link(page_url, link_href):
    # path components we care about when looking for links to click
    wanted_paths = ["news", "article", "articles", "story", "blog", "world",
                    "video", "videos", "media", "artikel", "news-story",
                    "noticias", "actualite", "actualites", "nachrichten",
                    "nyheter", "noticia", "haber", "notizie"]
    today = datetime.today()
    start_year = today.year - 2
    wanted_paths = [
        str(year) for year in range(start_year, start_year + 3)
    ] + wanted_paths
    wanted_paths.append('{d.year}{d.month:02}{d.day:02}'.format(d=today))
    wanted_paths.append('{d.year}-{d.month:02}-{d.day:02}'.format(d=today))

    try:
        link_parts = urlparse(link_href)
    except ValueError:
        return False
    if link_parts.path == "/":
        return False

    # only keep links that point somewhere else within the site we are on
    if link_href.startswith(page_url):
        if link_href.startswith(page_url + '#'):
            return False

        # limit to news/blog/media articles for now
        if all('/' + x + '/' not in link_parts.path or link_parts.path.endswith('/' + x + '/') for x in wanted_paths):
            return False

    # also keep links that point to different news/blog/media
    # subdomains of the same base domain
    else:
        netloc_parts = link_parts.netloc.split('.')
        if netloc_parts[0] not in wanted_paths or not page_url.endswith('.'.join(netloc_parts[1:]) + '/'):
            return False

    # if there is a file extension, limit to allowed extensions
    ext = os.path.splitext(link_parts.path)[1]
    if ext and ext not in ('.html', '.php', '.htm', '.aspx', '.shtml', '.jsp', '.asp'):
        return False

    return True


class Crawler:
    def __init__(self, args):
        self.browser = args.browser
        self.browser_binary = args.browser_binary
        self.chromedriver_path = args.chromedriver_path
        self.domain_list = args.domain_list
        self.exclude = args.exclude
        self.firefox_tracking_protection = args.firefox_tracking_protection
        self.load_extension = args.load_extension
        self.no_blocking = args.no_blocking
        self.num_sites = args.num_sites
        self.out_dir = args.out_dir
        self.pb_dir = args.pb_dir
        self.take_screenshots = args.take_screenshots
        self.timeout = args.timeout
        self.wait_time = args.wait_time

        # version is based on when the crawl started
        self.version = time.strftime('%Y.%-m.%-d', time.localtime())

        # set up logging
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)
        log_fmt = logging.Formatter('%(asctime)s %(message)s')

        # by default, just log to file
        pathlib.Path(self.out_dir).mkdir(exist_ok=True)
        fh = logging.FileHandler(os.path.join(self.out_dir, 'log.txt'))
        fh.setFormatter(log_fmt)
        self.logger.addHandler(fh)

        # log to stdout as well if configured
        if args.log_stdout:
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(log_fmt)
            self.logger.addHandler(sh)

        self.last_data = None
        self.storage_objects = ['snitch_map', 'action_map', 'tracking_map']

        self.logger.info("Fetching TLD definitions ...")
        self.tld_extract = TLDExtract(cache_dir=False, include_psl_private_domains=True)

        self.start_browser()

        # collect Privacy Badger git info for logging
        def get_git_info(path):
            git_info = {
                'branch': None,
                'commit_hash': None
            }

            commit_hash = subprocess.check_output(
                "git rev-parse HEAD".split(" "),
                cwd=path, universal_newlines=True).strip()
            git_info['commit_hash'] = commit_hash

            branch = subprocess.check_output(
                "git rev-parse --abbrev-ref HEAD".split(" "),
                cwd=path, universal_newlines=True).strip()
            if branch != "HEAD":
                git_info['branch'] = branch

            return git_info

        git_data = get_git_info(self.pb_dir)

        self.logger.info(
            (
                "Starting new crawl:\n\n"
                "  browser: %s\n"
                "  Badger branch: %s\n"
                "  Badger hash: %s\n"
                "  blocking: %s\n"
                "  timeout: %ss\n"
                "  wait time: %ss\n"
                "  survey mode: %s\n"
                "  domain list: %s\n"
                "  domains to crawl: %d\n"
                "  suffixes to exclude: %s\n"
                "  parallel extension: %s\n"
                "  driver capabilities:\n\n%s\n"
            ),
            f"Firefox (ETP {self.firefox_tracking_protection})" if self.browser == FIREFOX else self.browser.capitalize(),
            git_data['branch'],
            git_data['commit_hash'],
            "off" if self.no_blocking else "standard",
            self.timeout,
            self.wait_time,
            args.survey,
            self.domain_list if self.domain_list else "Tranco " + TRANCO_VERSION,
            self.num_sites,
            self.exclude,
            self.load_extension,
            pformat(self.driver.capabilities)
        )

        # load tracker data from one or more Badger data JSON files
        for data_json in args.load_data:
            with open(data_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.load_user_data(data)

    def handle_alerts_and(self, fun):
        num_tries = 0

        while True:
            num_tries += 1
            try:
                res = fun()
                break
            except UnexpectedAlertPresentException as uape:
                if num_tries > MAX_ALERTS:
                    raise WebDriverException("Too many alerts") from uape
                # first dismiss, next time accept, then dismiss, ...
                dismiss_alert(self.driver, not bool(num_tries % 2))

        return res

    def get_firefox_options(self):
        opts = FirefoxOptions()

        if self.browser_binary:
            opts.binary_location = self.browser_binary

        #opts.log.level = "trace"

        opts.set_capability("acceptInsecureCerts", False);
        opts.set_capability("unhandledPromptBehavior", "ignore");

        opts.set_preference(
            'extensions.webextensions.uuids', f'{{"{FF_EXT_ID}": "{FF_UUID}"}}')

        opts.set_preference("dom.webdriver.enabled", False)

        # disable prefetching
        opts.set_preference("network.dns.disablePrefetch", True)
        opts.set_preference("network.prefetch-next", False)
        # disable OpenH264 codec downloading
        opts.set_preference("media.gmp-gmpopenh264.enabled", False)
        opts.set_preference("media.gmp-manager.url", "")
        # disable health reports
        opts.set_preference("datareporting.healthreport.service.enabled", False)
        opts.set_preference("datareporting.healthreport.uploadEnabled", False)
        opts.set_preference("datareporting.policy.dataSubmissionEnabled", False)
        # disable experiments
        opts.set_preference("experiments.enabled", False)
        opts.set_preference("experiments.supported", False)
        opts.set_preference("experiments.manifest.uri", "")
        # disable telemetry
        opts.set_preference("toolkit.telemetry.enabled", False)
        opts.set_preference("toolkit.telemetry.unified", False)
        opts.set_preference("toolkit.telemetry.archive.enabled", False)

        if self.firefox_tracking_protection == "off":
            # disable all content blocking/Tracking Protection features
            # https://wiki.mozilla.org/Security/Tracking_protection
            opts.set_preference("privacy.trackingprotection.enabled", False)
            opts.set_preference("privacy.trackingprotection.pbmode.enabled", False)
            opts.set_preference("privacy.trackingprotection.cryptomining.enabled", False)
            opts.set_preference("privacy.trackingprotection.fingerprinting.enabled", False)
            opts.set_preference("privacy.trackingprotection.socialtracking.enabled", False)
            # always allow third-party cookies
            opts.set_preference("network.cookie.cookieBehavior", 0)
        elif self.firefox_tracking_protection == "strict":
            opts.set_preference("browser.contentblocking.category", "strict")

        return opts

    def start_driver(self):
        """Start a new Selenium web driver and install the bundled
        extension."""
        if self.browser in (CHROME, EDGE):
            # make extension ID constant across runs

            # create temp directory
            # TODO does tmp_dir actually get cleaned up?
            self.tmp_dir = tempfile.TemporaryDirectory() # pylint:disable=consider-using-with
            new_extension_path = os.path.join(self.tmp_dir.name, "src")

            # copy extension sources there
            copytree(os.path.join(self.pb_dir, 'src'), new_extension_path)

            # update manifest.json
            manifest_path = os.path.join(new_extension_path, "manifest.json")
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            # this key and the extension ID
            # must both be derived from the same private key
            manifest['key'] = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArMdgFkGsm7nOBr/9qkx8XEcmYSu1VkIXXK94oXLz1VKGB0o2MN+mXL/Dsllgkh61LZgK/gVuFFk89e/d6Vlsp9IpKLANuHgyS98FKx1+3sUoMujue+hyxulEGxXXJKXhk0kGxWdE0IDOamFYpF7Yk0K8Myd/JW1U2XOoOqJRZ7HR6is1W6iO/4IIL2/j3MUioVqu5ClT78+fE/Fn9b/DfzdX7RxMNza9UTiY+JCtkRTmm4ci4wtU1lxHuVmWiaS45xLbHphQr3fpemDlyTmaVoE59qG5SZZzvl6rwDah06dH01YGSzUF1ezM2IvY9ee1nMSHEadQRQ2sNduNZWC9gwIDAQAB" # noqa:E501 pylint:disable=line-too-long

            # remove the 5MB limit on Chrome extension local storage
            if 'unlimitedStorage' not in manifest['permissions']:
                manifest['permissions'].append('unlimitedStorage')

            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f)

            opts = ChromeOptions() if self.browser == CHROME else EdgeOptions()

            if self.browser_binary:
                opts.binary_location = self.browser_binary

            opts.add_argument("--load-extension=" + new_extension_path)

            # loads parallel extension to run alongside pb
            if self.load_extension:
                opts.add_extension(self.load_extension)

            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--disable-crash-reporter")

            opts.set_capability("acceptInsecureCerts", False);
            opts.set_capability("unhandledPromptBehavior", "ignore");

            for _ in range(5):
                try:
                    if self.browser == CHROME:
                        self.driver = webdriver.Chrome(self.chromedriver_path, options=opts)
                    else:
                        self.driver = webdriver.Edge(options=opts)
                except ConnectionResetError as e:
                    self.logger.warning((
                        "%s WebDriver initialization failed:\n"
                        "%s\n"
                        "Retrying ..."), self.browser.capitalize(), str(e))
                    time.sleep(2)
                else:
                    break

        elif self.browser == FIREFOX:
            opts = self.get_firefox_options()
            service = FirefoxService(log_path=os.path.devnull)
            self.driver = webdriver.Firefox(options=opts, service=service)

            # load Privacy Badger
            # Firefox requires absolute paths
            unpacked_addon_path = os.path.abspath(
                os.path.join(self.pb_dir, 'src'))
            self.driver.install_addon(unpacked_addon_path, temporary=True)

            # loads parallel extension to run alongside pb
            if self.load_extension:
                parallel_extension_url = os.path.abspath(self.load_extension)
                self.driver.install_addon(parallel_extension_url)

        # apply timeout settings
        self.driver.set_page_load_timeout(self.timeout)
        self.driver.set_script_timeout(self.timeout)

        self.driver.maximize_window()

        # wait for Badger to finish initializing
        self.load_extension_page()
        wait_for_script(self.driver, (
            "let done = arguments[arguments.length - 1];"
            "chrome.runtime.sendMessage({"
            "  type: 'isBadgerInitialized'"
            "}, r => done(r));"), execute_async=True)
        # also disable the welcome page
        self.driver.execute_async_script(
            "let done = arguments[arguments.length - 1];"
            "chrome.runtime.sendMessage({"
            "  type: 'updateSettings',"
            "  data: { showIntroPage: false }"
            "}, done);")

    def load_extension_page(self, tries=3):
        """Loads Privacy Badger's options page."""

        if self.browser in (CHROME, EDGE):
            url = f'{CHROME_URL_PREFIX}{CHROME_EXT_ID}/skin/options.html'
        elif self.browser == FIREFOX:
            url = f'{FF_URL_PREFIX}{FF_UUID}/skin/options.html'

        def _load_ext_page():
            self.driver.get(url)
            # wait for extension page to be ready
            wait_for_script(self.driver, "return chrome.extension")

        num_timeouts = 0

        for _ in range(tries):
            try:
                self.handle_alerts_and(_load_ext_page)
                break
            except (MaxRetryError, ProtocolError) as e:
                self.logger.warning("Error loading extension page:\n%s", str(e))
                self.restart_browser()
            except TimeoutException:
                num_timeouts += 1
                self.logger.warning("Timed out loading extension page")
            except WebDriverException as err:
                self.logger.warning("Error loading extension page (%s): %s", type(err).__name__, err.msg)
                if should_restart(err):
                    self.restart_browser()
        else:
            if num_timeouts >= tries:
                self.restart_browser()
            raise WebDriverException("Failed to load extension page")

    def load_user_data(self, data):
        """Load saved user data into Privacy Badger after a restart"""
        self.load_extension_page()

        # TODO migrate away from getBackgroundPage()
        # TODO add message that calls mergeUserData only, no blockWidgetDomains or anything else
        self.driver.execute_script(
            "(function (data) {"
            "  let bg = chrome.extension.getBackgroundPage();"
            "  bg.badger.mergeUserData(data);"
            "}(arguments[0]));", data)

        # force Badger data to get written to disk
        for store_name in self.storage_objects:
            self.driver.execute_async_script((
                "let done = arguments[arguments.length - 1];"
                "chrome.runtime.sendMessage({"
                "  type: 'syncStorage',"
                "  storeName: arguments[0]"
                "}, done);"), store_name)

    def dump_data(self):
        """Extract the objects Privacy Badger learned during its training
        run."""
        data = {}
        self.load_extension_page()
        for store_name in self.storage_objects:
            data[store_name] = self.driver.execute_async_script((
                "let done = arguments[arguments.length - 1],"
                "  store_name = arguments[0];"
                "chrome.runtime.sendMessage({"
                "  type: 'syncStorage',"
                "  storeName: store_name"
                "}, function () {"
                "  chrome.storage.local.get([store_name], function (res) {"
                "    done(res[store_name]);"
                "  });"
                "});"
            ), store_name)
        return data

    def clear_data(self):
        """Clear the training data Privacy Badger starts with."""
        self.load_extension_page()
        self.driver.execute_async_script((
            "let done = arguments[arguments.length - 1];"
            "chrome.runtime.sendMessage({"
            "  type: 'removeAllData'"
            "}, done);"
        ))

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

        error_text = self.driver.find_element(By.TAG_NAME, "body").text
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

    def take_screenshot(self, domain):
        pathlib.Path(self.out_dir + '/screenshots').mkdir(exist_ok=True)
        filename = os.path.join(self.out_dir, "screenshots", "".join((
            str(int(time.time())),
            "-",
            re.sub(r'[^a-z0-9]', '-', domain.lower()[:100]),
            ".png")))
        if not self.driver.save_screenshot(filename):
            self.logger.warning("Failed to save screenshot for %s", domain)

    def scroll_page(self):
        # split self.wait_time into INTERVAL_SEC intervals
        INTERVAL_SEC = 0.1
        for _ in range(int(self.wait_time / INTERVAL_SEC)):
            time.sleep(INTERVAL_SEC)

            # scroll a bit during every interval
            # dismiss any modal dialogs (alerts)
            while True:
                try:
                    self.driver.execute_script("window.scrollBy(0, arguments[0]);",
                        abs(random.normalvariate(50, 25)))
                    break
                except UnexpectedAlertPresentException:
                    dismiss_alert(self.driver)

    def gather_internal_links(self):
        links = []
        curl = self.driver.current_url

        for i, el in enumerate(self.driver.find_elements(By.TAG_NAME, 'a')):
            # limit to checking 200 links
            if i > 199:
                break

            try:
                href = el.get_property('href')
            except StaleElementReferenceException:
                continue

            if not href:
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

            if not href.startswith("http") or not internal_link(curl, href):
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
        if not links or len(links) < 10:
            return

        # sort by link length (try to prioritize article links)
        links.sort(key=lambda item: (-len(item[0]), item[0]))
        # take top ten
        links = links[:10]

        link_href, link_el = random.choice(links)
        self.logger.info("Clicking on %s", link_href)
        try:
            curl = self.driver.current_url
            cwindows = self.driver.window_handles

            try:
                link_el.click()
            except (ElementClickInterceptedException, ElementNotInteractableException, ElementNotVisibleException):
                self.driver.execute_script("arguments[0].click()", link_el)

            try:
                WebDriverWait(self.driver, 15).until(EC.any_of(
                    EC.url_changes(curl),
                    EC.new_window_is_opened(cwindows)))
            except TimeoutException:
                pass
        except WebDriverException as e:
            self.logger.error(
                "Failed to visit link (%s): %s", type(e).__name__, e.msg)
        else:
            # TODO wait for the page to actually load first
            self.scroll_page()

    def get_domain(self, domain):
        """
        Visit a domain, then spend `self.wait_time` seconds on the site
        waiting for dynamic loading to complete.
        """

        url = f"http://{domain}/"

        self.handle_alerts_and(lambda: self.driver.get(url))

        self.raise_on_chrome_error_pages()
        self.raise_on_security_pages()

        self.scroll_page()

        self.click_internal_link()

        # if any new tabs/windows got opened, close them now
        handles = self.driver.window_handles
        if len(list(handles)) > 1:
            for handle in handles[1:]:
                self.driver.switch_to.window(handle)
                if self.take_screenshots:
                    self.take_screenshot(domain + "-" + self.driver.current_url)
                self.driver.close()
            self.driver.switch_to.window(handles[0])

        if self.take_screenshots:
            self.take_screenshot(domain + "-" + self.driver.current_url)

        return url

    def get_domain_list(self):
        """Get the top n sites from the Tranco list"""
        domains = []
        num_sites = self.num_sites if self.num_sites else DEFAULT_NUM_SITES

        if self.domain_list:
            # read in domains from file
            with open(self.domain_list, encoding="utf-8") as f:
                for line in f:
                    domain = line.strip()
                    if domain and domain[0] != '#':
                        domains.append(domain)
        else:
            self.logger.info("Fetching Tranco list ...")
            domains = Tranco(cache=False).list(TRANCO_VERSION).top()

        if self.exclude:
            filtered_domains = []

            # gather domains that don't end with any of the "exclude" suffixes
            for domain in domains:
                if not any(domain.endswith(suffix) for suffix in self.exclude.split(",")):
                    filtered_domains.append(domain)
                # return the list if we gathered enough
                if len(filtered_domains) == num_sites:
                    return filtered_domains

            return filtered_domains

        # if no exclude option is passed in, just return top n domains from list
        return domains[:num_sites]

    def start_browser(self):
        self.start_driver()

        self.clear_data()

        self.load_extension_page()

        if self.no_blocking:
            # set blocking threshold to infinity,
            # to never learn to block (and create unlimited snitch_map entries)
            self.driver.execute_script(
                "chrome.runtime.sendMessage({"
                "  type: 'setBlockThreshold',"
                "  value: Number.MAX_VALUE"
                "})")

        # enable local learning
        wait_for_script(self.driver, "return window.OPTIONS_INITIALIZED")
        try:
            self.driver.find_element(By.ID, 'local-learning-checkbox').click()
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

    def log_snitch_map_changes(self, old_snitches, new_snitches):
        diff = set(new_snitches) - set(old_snitches)
        if diff:
            self.logger.info("New domains in snitch_map: %s", ', '.join(sorted(diff)))

    def crawl(self):
        """
        Visit the top `num_sites` websites in the Tranco list, in order, in
        a virtual browser with Privacy Badger installed. Afterwards, save the
        action_map and snitch_map that the Badger learned.
        """

        if self.num_sites == 0:
            domains = []
        else:
            domains = self.get_domain_list()

        # list of domains we actually visited
        visited = []
        old_snitches = self.dump_data()['snitch_map']

        random.shuffle(domains)

        for i, domain in enumerate(domains):
            try:
                if self.last_data:
                    old_snitches = self.last_data['snitch_map']

                # This script could fail during the data dump (trying to get
                # the options page), the data cleaning, or while trying to load
                # the next domain.
                self.last_data = self.dump_data()

                self.log_snitch_map_changes(old_snitches, self.last_data['snitch_map'])

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
            except (MaxRetryError, ProtocolError) as e:
                self.logger.warning("Error loading %s:\n%s", domain, str(e))
                self.restart_browser()
            except TimeoutException:
                self.logger.warning("Timed out loading %s", domain)
            except WebDriverException as e:
                self.logger.error("%s on %s: %s", type(e).__name__, domain, e.msg)
                if should_restart(e):
                    self.restart_browser()

        num_total = len(domains)
        if num_total:
            num_successes = len(visited)
            num_errors = num_total - num_successes
            self.logger.info(
                "Finished scan. Visited %d sites and errored on %d (%.1f%%)",
                num_successes, num_errors, (num_errors / num_total * 100)
            )

        try:
            if self.last_data:
                old_snitches = self.last_data['snitch_map']
            data = self.dump_data()
            self.log_snitch_map_changes(old_snitches, data['snitch_map'])
        except WebDriverException as e:
            # If we can't load the options page here, just quit :(
            self.logger.error(
                "Could not get Badger storage!\n"
                "%s: %s", type(e).__name__, e.msg)
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

        # TODO once the need for this is gone, should be able to get rid of tldextract, in this script anyway
        d1_base = self.tld_extract(d1).registered_domain
        if not d1_base:
            d1_base = d1

        # handle the domain-attribution bug (Privacy Badger issue #1997).
        # If a domain we visited was recorded as a tracker on the domain we
        # visited immediately after it, it's probably a bug
        if d1_base in snitch_map and d2 in snitch_map[d1_base]:
            self.logger.info("Likely bug: domain %s tracking on %s", d1_base, d2)
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
        with open(os.path.join(self.out_dir, name), 'w', encoding="utf-8") as f:
            json.dump(
                data, f, indent=2, sort_keys=True, separators=(',', ': '))
        self.logger.info("Saved data to %s", name)


class SurveyCrawler(Crawler):
    def __init__(self, args):
        super().__init__(args)

        self.max_data_size = args.max_data_size
        self.storage_objects = ['snitch_map']

    def set_passive_mode(self):
        self.load_extension_page()
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

    # TODO use --load-data instead?
    def merge_saved_data(self):
        paths = glob.glob(os.path.join(self.out_dir, 'results-*.json'))
        snitch_map = {}
        for p in paths:
            with open(p, encoding='utf-8') as f:
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
        Visit the top `num_sites` websites in the Tranco list, in order, in
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
                    self.save(self.last_data, f'results-{first_i}-{i}.json')
                    first_i = i + 1
                    self.last_data = {}
                    self.restart_browser()

                self.logger.info("Visiting %d: %s", i + 1, domain)
                url = self.get_domain(domain)
                visited.append(url)
            except (MaxRetryError, ProtocolError) as e:
                self.logger.warning("Error loading %s:\n%s", domain, str(e))
                self.restart_browser()
            except TimeoutException:
                self.logger.warning("Timed out loading %s", domain)
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
                    "%s: %s\nUsing cached data ...",
                    type(e).__name__, e.msg)
                data = self.last_data
            else:
                self.logger.error("Could not export data:\n%s", e.msg)
                sys.exit(1)

        self.driver.quit()

        self.save(data, f'results-{first_i}-{i}.json')
        self.save(self.merge_saved_data())


if __name__ == '__main__':
    args = ap.parse_args()

    # create an XVFB virtual display (to avoid opening an actual browser)
    with Xvfb(width=1920, height=1200) if not args.no_xvfb else contextlib.suppress():
        if args.survey:
            crawler = SurveyCrawler(args)
        else:
            crawler = Crawler(args)

        crawler.crawl()
