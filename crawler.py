#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
# adapted from https://github.com/cowlicks/badger-claw
import argparse
import copy
import glob
import hashlib
import json
import logging
import os
import struct
import string
import sys
import time
from urllib.request import urlopen

from PyFunceble import test as PyFunceble
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException,\
                                       NoSuchWindowException,\
                                       SessionNotCreatedException,\
                                       JavascriptException
from selenium.webdriver.chrome.options import Options
from tldextract import TLDExtract
from xvfbwrapper import Xvfb


CHROME_URL_FMT = 'chrome-extension://%s/'
CHROMEDRIVER_PATH='/usr/bin/chromedriver'
FF_URL_FMT = 'moz-extension://%s/'
FF_EXT_ID = 'jid1-MnnxcxisBPnSXQ@jetpack'
FF_UUID = 'd56a5b99-51b6-4e83-ab23-796216679614'
FF_BIN_PATH = '/usr/bin/firefox'
BACKGROUND = '_generated_background_page.html'
OPTIONS = 'skin/options.html'

CHROME = 'chrome'
FIREFOX = 'firefox'

MAJESTIC_URL = "http://downloads.majesticseo.com/majestic_million.csv"
WEEK_IN_SECONDS = 604800
RESTART_RETRIES = 5

ap = argparse.ArgumentParser()
ap.add_argument('--browser', choices=[FIREFOX, CHROME], default=FIREFOX,
                help='Browser to use for the scan')
ap.add_argument('--n-sites', type=int, default=2000,
                help='Number of websites to visit on the crawl')
ap.add_argument('--timeout', type=float, default=30,
                help='Amount of time to allow each site to load, in seconds')
ap.add_argument('--wait-time', type=float, default=5,
                help='Amount of time to wait on each site after it loads, in seconds')
ap.add_argument('--log-stdout', action='store_true', default=False,
                help='If set, log to stdout as well as log.txt')
ap.add_argument('--survey', action='store_true', default=False,
                help="If set, don't block anything or store action_map data")
ap.add_argument('--max-data-size', type=int, default=5e5,
                help='Maximum size of serialized localstorage data')

# Arguments below here should never have to be used within the docker container.
ap.add_argument('--out-path', default='./',
                help='Path at which to save output')
ap.add_argument('--ext-path', default='./privacybadger/src',
                help='Path to the Privacy Badger binary or source directory')
ap.add_argument('--chromedriver-path', default=CHROMEDRIVER_PATH,
                help='Path to the chromedriver binary')
ap.add_argument('--firefox-path', default=FF_BIN_PATH,
                help='Path to the firefox browser binary')


# Force a 'Failed to decode response from marionette' crash.
# Example from this ticket: https://bugzilla.mozilla.org/show_bug.cgi?id=1401131
def test_crash(driver):
    driver.set_context("chrome")
    driver.execute_script("""
// Copied from crash me simple
Components.utils.import("resource://gre/modules/ctypes.jsm");

// ctypes checks for NULL pointer derefs, so just go near-NULL.
var zero = new ctypes.intptr_t(8);
var badptr = ctypes.cast(zero, ctypes.PointerType(ctypes.int32_t));
var crash = badptr.contents;""")


def get_chrome_extension_id(crx_file):
    """Interpret a .crx file's extension ID"""
    with open(crx_file, 'rb') as f:
        data = f.read()
    header = struct.unpack('<4sIII', data[:16])
    pubkey = struct.unpack('<%ds' % header[2], data[16:16+header[2]])[0]

    digest = hashlib.sha256(pubkey).hexdigest()

    trans = str.maketrans('0123456789abcdef', string.ascii_lowercase[:16])
    return str.translate(digest[:32], trans)


def get_domain_list(n_sites, out_path):
    """Load the top million domains from disk or the web"""
    top_1m_file = os.path.join(out_path, MAJESTIC_URL.split('/')[-1])
    pyfunc_cache_file = os.path.join(out_path, 'pyfunceable_cache.json')

    # download the file if it doesn't exist or if it's more than a week stale
    if (not os.path.exists(top_1m_file) or
            time.time() - os.path.getmtime(top_1m_file) > WEEK_IN_SECONDS):
        logger.info('Loading new Majestic data and refreshing PyFunceble cache')
        response = urlopen(MAJESTIC_URL)
        with open(top_1m_file, 'w') as f:
            f.write(response.read().decode())

        # if the majestic file is expired, let's refresh the pyfunceable cache
        if os.path.exists(pyfunc_cache_file):
            os.remove(pyfunc_cache_file)

    # load cache
    if os.path.exists(pyfunc_cache_file):
        with open(pyfunc_cache_file) as f:
            pyfunc_cache = json.load(f)
    else:
        pyfunc_cache = {}

    domains = []
    with open(top_1m_file) as f:
        # first line is CSV header
        next(f)

        # only read the first n_sites lines
        for l in f:
            domain = l.split(',')[2]

            if domain in pyfunc_cache:
                if pyfunc_cache[domain] == 'ACTIVE':
                    domains.append(domain)
            else:
                status = PyFunceble(domain)
                logger.info('PyFunceble: %s is %s', domain, status)
                if status == 'ACTIVE':
                    domains.append(domain)
                pyfunc_cache[domain] = status

            if len(domains) >= n_sites:
                break

    # save pyfunceble cache again
    with open(pyfunc_cache_file, 'w') as f:
        json.dump(pyfunc_cache, f)

    return domains

def size_of(data):
    """Get the size (in bytes) of the serialized data structure"""
    return len(json.dumps(data))


class Crawler(object):
    def __init__(self, browser, n_sites, timeout, wait_time, log_stdout,
                 out_path, ext_path, chromedriver_path, firefox_path,
                 **kwargs):
        self.browser = browser
        self.n_sites = n_sites
        self.timeout = timeout
        self.wait_time = wait_time
        self.out_path = out_path
        self.ext_path = ext_path
        self.chromedriver_path = chromedriver_path
        self.firefox_path = firefox_path

        # version is based on when the crawl started
        self.version = time.strftime('%Y.%-m.%-d', time.localtime())

        # set up logging
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)
        log_fmt = logging.Formatter('%(asctime)s %(message)s')

        # by default, just log to file
        fh = logging.FileHandler(os.path.join(out_path, 'log.txt'))
        fh.setFormatter(log_fmt)
        self.logger.addHandler(fh)

        # log to stdout if configured
        if log_stdout:
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(log_fmt)
            self.logger.addHandler(sh)

        self.storage_objects = ['action_map', 'snitch_map']

    def start_driver(self):
        """Start a new Selenium web driver and install the bundled extension."""
        if self.browser == CHROME:
            opts = Options()
            opts.add_argument('--no-sandbox')
            opts.add_extension(self.ext_path)
            prefs = {"profile.block_third_party_cookies": False}
            opts.add_experimental_option("prefs", prefs)
            opts.add_argument('--dns-prefetch-disable')
            self.driver = webdriver.Chrome(self.chromedriver_path,
                                           chrome_options=opts)

        elif self.browser == FIREFOX:
            profile = webdriver.FirefoxProfile()
            profile.set_preference('extensions.webextensions.uuids',
                                   '{"%s": "%s"}' % (FF_EXT_ID, FF_UUID))

            # this is kind of a hack; eventually the functionality to install an
            # extension should be part of Selenium. See
            # https://github.com/SeleniumHQ/selenium/issues/4215
            self.driver = webdriver.Firefox(firefox_profile=profile,
                                            firefox_binary=self.firefox_path)
            command = 'addonInstall'
            info = ('POST', '/session/$sessionId/moz/addon/install')
            self.driver.command_executor._commands[command] = info
            self.driver.execute(command, params={'path': self.ext_path,
                                                 'temporary': True})
            time.sleep(2)

        else:
            raise ValueError("%s is not a valid browser" % self.browser)

        # apply timeout settings
        self.driver.set_page_load_timeout(self.timeout)
        self.driver.set_script_timeout(self.timeout)

    def load_extension_page(self, page, retries=3):
        """
        Load a page in the Privacy Badger extension. `page` should either be
        BACKGROUND or OPTIONS.
        """
        if self.browser == CHROME:
            ext_url = (CHROME_URL_FMT + page) % get_chrome_extension_id(ext_path)
        else:
            ext_url = (FF_URL_FMT + page) % FF_UUID

        for _ in range(retries):
            try:
                self.driver.get(ext_url)
                break
            except WebDriverException as e:
                err = e
        else:
            self.logger.error('Error loading extension page: %s', err.msg)
            raise err

    def load_user_data(self, data):
        """Load saved user data into Privacy Badger after a restart"""
        self.load_extension_page(OPTIONS)
        for obj in self.storage_objects:
            script = '''
data = JSON.parse(arguments[0]);
badger.storage.%s.merge(data.%s);''' % (obj, obj)
            self.driver.execute_script(script, json.dumps(data))

        time.sleep(2)   # wait for localstorage to sync

    def dump_data(self):
        """Extract the objects Privacy Badger learned during its training run."""
        self.load_extension_page(BACKGROUND)

        data = {}
        for obj in self.storage_objects:
            script = 'return badger.storage.%s.getItemClones()' % obj
            data[obj] = self.driver.execute_script(script)
        return data

    def clear_data(self):
        """Clear the training data Privacy Badger starts with."""
        self.load_extension_page(OPTIONS)
        self.js("badger.storage.clearTrackerData();")

    def timeout_workaround(self):
        """
        Selenium has a bug where a tab that raises a timeout exception can't
        recover gracefully. So we kill the tab and make a new one.
        TODO: find actual bug ticket
        """
        self.driver.close()  # kill the broken site
        self.driver.switch_to_window(self.driver.window_handles.pop())
        before = set(self.driver.window_handles)
        self.driver.execute_script('window.open()')

        new_window = (set(self.driver.window_handles) ^ before).pop()
        self.driver.switch_to_window(new_window)

    def get_domain(self, domain):
        """
        Try to load a domain over https, and fall back to http if the initial load
        times out. Then sleep `wait_time` seconds on the site to wait for AJAX calls
        to complete.
        """
        try:
            url = "https://%s/" % domain
            self.driver.get(url)
        except TimeoutException:
            self.logger.info('timeout on %s ', url)
            self.timeout_workaround()
            url = "http://%s/" % domain
            self.logger.info('trying %s', url)
            self.driver.get(url)

        time.sleep(self.wait_time)
        return url

    def restart_browser(self, data):
        self.logger.info('restarting browser...')

        # It's ugly, but this section needs to be ABSOLUTELY crash-proof.
        for _ in range(RESTART_RETRIES):
            try:
                self.driver.quit()
            except:
                pass

            try:
                del self.driver
            except:
                pass

            try:
                self.start_driver()
                self.load_user_data(data)
                self.logger.error('Success')
                break
            except Exception as e:
                self.logger.error('Error restarting browser. Trying again...')
                if type(e) == WebDriverException:
                    self.logger.error('%s: %s', type(e).__name__, e.msg)
                else:
                    self.logger.error('%s: %s', type(e).__name__, e)
        else:
            # If we couldn't restart the browser after all that, just quit.
            self.logger.error('Could not restart browser.')
            sys.exit(1)

    # determine whether we need to restart the webdriver after an error
    def should_restart(self, e):
        return (type(e) == NoSuchWindowException or
            type(e) == SessionNotCreatedException or
            'response from marionette' in e.msg)

    def crawl(self):
        """
        Visit the top `n_sites` websites in the Majestic Million, in order, in a
        virtual browser with Privacy Badger installed. Afterwards, save the
        action_map and snitch_map that the Badger learned.
        """
        domains = get_domain_list(self.n_sites, self.out_path)
        self.logger.info('starting new crawl with timeout %s n_sites %s',
                         self.timeout, self.n_sites)

        # create an XVFB virtual display (to avoid opening an actual browser)
        self.vdisplay = Xvfb(width=1280, height=720)
        self.vdisplay.start()
        self.start_driver()

        # list of domains we actually visited
        visited = []

        for i, domain in enumerate(domains):
            try:
                last_data = self.dump_data()
                self.logger.info('visiting %d: %s', i + 1, domain)
                url = self.get_domain(domain)
                visited.append(url)
            except TimeoutException:
                self.logger.info('timeout on %s ', domain)
                # TODO: how to get rid of this nested try?
                try:
                    self.timeout_workaround()
                except WebDriverException as e:
                    if self.should_restart(e):
                        self.restart_browser(last_data)
            except WebDriverException as e:
                self.logger.error('%s %s: %s', domain, type(e).__name__, e.msg)
                if self.should_restart(e):
                    self.restart_browser(last_data)

        self.logger.info('Finished scan. Visited %d sites and errored on %d.',
                    len(visited), len(domains) - len(visited))

        try:
            self.logger.info('Getting data from browser storage...')
            data = self.dump_data()
        except WebDriverException:
            # If we can't load the background page here, just quit :(
            self.logger.error('Could not get badger storage.')
            sys.exit(1)

        self.driver.quit()
        self.vdisplay.stop()

        self.cleanup(domains, data)
        self.save(self.merge_saved_data())

    def cleanup(self, domains, data):
        """
        Remove from snitch map any domains that appear to have been added as a
        result of bugs.
        """
        self.logger.info('Cleaning data...')

        snitch_map = data['snitch_map']
        action_map = data['action_map']

        # handle blank domain bug
        if '' in action_map:
            self.logger.info('Deleting blank domain from action map')
            del action_map['']

        if '' in snitch_map:
            self.logger.info('Deleting blank domain from snitch map')
            del snitch_map['']

        # handle the domain-attribution bug (Privacy Badger issue #1997).
        for i in range(len(domains) - 1):
            d1, d2 = domains[i:i+2]

            # If a domain we visited was recorded as a tracker on the domain we
            # visited immediately after it, it's probably a bug
            if d1 in snitch_map and d2 in snitch_map[d1]:
                self.logger.info('Reported domain %s tracking on %s', d1, d2)
                snitch_map[d1].remove(d2)

                # if the bug caused d1 to be added to the action map, remove it
                if not snitch_map[d1]:
                    self.logger.info('Deleting domain %s from action and snitch maps',
                                d1)
                    del action_map[d1]
                    del snitch_map[d1]

                # if the bug caused d1 to be blocked, unblock it
                elif len(snitch_map[d1]) == 2:
                    self.logger.info('Downgrading domain %s from "block" to "allow"',
                                d1)
                    action_map[d1]['heuristicAction'] = 'allow'

    def save(self, data, name='results.json'):
        data['version'] = self.version

        self.logger.info('Saving seed data version %s...', self.version)
        # save the snitch_map in a human-readable JSON file
        with open(os.path.join(self.out_path, name), 'w') as f:
            json.dump(data, f, indent=2, sort_keys=True, separators=(',', ': '))
        self.logger.info('Saved data to %s.', name)


class SurveyCrawler(Crawler):
    def __init__(self, **kwargs):
        super(SurveyCrawler, self).__init__(**kwargs)

        self.max_data_size = kwargs.get('max_data_size')
        self.storage_objects = ['snitch_map']

    def set_passive_mode(self):
        self.load_extension_page(OPTIONS)
        script = '''
chrome.runtime.sendMessage({
    type: "updateSettings",
    data: { passiveMode: true }
});'''
        self.driver.execute_script(script)

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
        Visit the top `n_sites` websites in the Majestic Million, in order, in a
        virtual browser with Privacy Badger installed. Afterwards, save the
        and snitch_map that the Badger learned.
        """
        domains = get_domain_list(self.n_sites, self.out_path)
        self.logger.info('starting new crawl with timeout %s n_sites %s',
                         self.timeout, self.n_sites)

        # create an XVFB virtual display (to avoid opening an actual browser)
        self.vdisplay = Xvfb(width=1280, height=720)
        self.vdisplay.start()
        self.start_driver()

        # don't block anything, just listen and log
        self.set_passive_mode()

        # list of domains we actually visited
        visited = []
        last_data = None
        first_i = 0

        for i, domain in enumerate(domains):
            # If we can't load the options page for some reason, treat it like
            # any other error
            try:
                # save the state of privacy badger before we do anything else
                last_data = self.dump_data()

                # If the localstorage data is getting too big, dump it and restart
                if size_of(last_data) > self.max_data_size:
                    self.save(last_data, 'results-%d-%d.json' % (first_i, i))
                    first_i = i + 1
                    last_data = {}
                    self.restart_browser(last_data)

                self.logger.info('visiting %d: %s', i + 1, domain)
                url = self.get_domain(domain)
                visited.append(url)
            except TimeoutException:
                self.logger.info('timeout on %s ', domain)
                # TODO: how to get rid of this nested try?
                try:
                    self.timeout_workaround()
                except WebDriverException as e:
                    if self.should_restart(e):
                        self.restart_browser(last_data)
            except WebDriverException as e:
                self.logger.error('%s %s: %s', domain, type(e).__name__, e.msg)
                if self.should_restart(e):
                    self.restart_browser(last_data)
            except KeyboardInterrupt:
                self.logger.warn('Keyboard interrupt. Ending scan after %d sites.', i+1)
                break

        self.logger.info('Finished scan. Visited %d sites and errored on %d.',
                         len(visited), i + 1 - len(visited))
        self.logger.info('Getting data from browser storage...')

        try:
            self.logger.info('Getting data from browser storage...')
            data = self.dump_data()
        except WebDriverException:
            if last_data:
                self.logger.error('Could not get badger storage. Using cached data...')
                data = last_data
            else:
                self.logger.error('Could not export data. Exiting.')
                sys.exit(1)

        self.driver.quit()
        self.vdisplay.stop()

        self.save(data, 'results-%d-%d.json' % (first_i, i))
        self.save(self.merge_saved_data())


if __name__ == '__main__':
    # the argparse arguments must match the function signature of crawl()
    args = ap.parse_args()

    if args.survey:
        crawler = SurveyCrawler(**vars(ap.parse_args()))
    else:
        crawler = Crawler(**vars(ap.parse_args()))

    crawler.crawl()
