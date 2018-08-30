#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
# adapted from https://github.com/cowlicks/badger-claw
import argparse
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

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException,\
                                       NoSuchWindowException,\
                                       SessionNotCreatedException,\
                                       JavascriptException
from selenium.webdriver.chrome.options import Options
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

OBJECTS = ['snitch_map']
MAJESTIC_URL = "http://downloads.majesticseo.com/majestic_million.csv"
WEEK_IN_SECONDS = 604800
RETRIES = 5

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
      var crash = badptr.contents;
    """)


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
    domains = []

    top_1m_file = os.path.join(out_path, MAJESTIC_URL.split('/')[-1])

    # download the file if it doesn't exist or if it's more than a week stale
    if (not os.path.exists(top_1m_file) or
            time.time() - os.path.getmtime(top_1m_file) > WEEK_IN_SECONDS):
        response = urlopen(MAJESTIC_URL)
        with open(top_1m_file, 'w') as f:
            f.write(response.read().decode())

    with open(top_1m_file) as f:
        # first line is CSV header
        next(f)

        # only read the first n_sites lines
        for i, l in enumerate(f):
            if i >= n_sites:
                break
            domains.append(l.split(',')[2])

    return domains


def start_driver_chrome(ext_path, chromedriver_path):
    """Start a new Selenium web driver for Chrome and install the bundled extension."""
    opts = Options()
    opts.add_argument('--no-sandbox')
    opts.add_extension(ext_path)
    opts.add_experimental_option("prefs", {"profile.block_third_party_cookies": False})
    opts.add_argument('--dns-prefetch-disable')
    driver = webdriver.Chrome(chromedriver_path, chrome_options=opts)

    set_passive_mode(driver, CHROME, ext_path)
    return driver


def start_driver_firefox(ext_path, browser_path):
    """Start a new Selenium web driver and install the bundled extension."""
    profile = webdriver.FirefoxProfile()
    profile.set_preference('extensions.webextensions.uuids',
                           '{"%s": "%s"}' % (FF_EXT_ID, FF_UUID))

    # this is kind of a hack; eventually the functionality to install an
    # extension should be part of Selenium. See
    # https://github.com/SeleniumHQ/selenium/issues/4215
    driver = webdriver.Firefox(firefox_profile=profile, firefox_binary=browser_path)
    command = 'addonInstall'
    driver.command_executor._commands[command] = ('POST', '/session/$sessionId/moz/addon/install')
    driver.execute(command, params={'path': ext_path, 'temporary': True})
    time.sleep(2)

    set_passive_mode(driver, FIREFOX, ext_path)
    return driver


def load_extension_page(driver, browser, ext_path, page, retries=3):
    """
    Load a page in the Privacy Badger extension. `page` should either be
    BACKGROUND or OPTIONS.
    """
    if browser == CHROME:
        ext_url = (CHROME_URL_FMT + page) % get_chrome_extension_id(ext_path)
    else:
        ext_url = (FF_URL_FMT + page) % FF_UUID

    for _ in range(retries):
        try:
            driver.get(ext_url)
            break
        except WebDriverException as e:
            err = e
    else:
        logger.error('Error loading extension page: %s', err.msg)
        raise err


def set_passive_mode(driver, browser, ext_path):
    load_extension_page(driver, browser, ext_path, OPTIONS)
    script = '''
chrome.runtime.sendMessage({
    type: "updateSettings",
    data: { passiveMode: true }
});'''
    driver.execute_script(script)


def load_user_data(driver, browser, ext_path, data):
    load_extension_page(driver, browser, ext_path, OPTIONS)
    script = '''
data = JSON.parse(arguments[0]);
badger.storage.snitch_map.merge(data.snitch_map);
'''
    driver.execute_script(script, json.dumps(data))
    time.sleep(2)   # wait for localstorage to sync


def clear_data(driver, browser, ext_path):
    """Clear Privacy Badger's local storage"""
    load_extension_page(driver, browser, ext_path, BACKGROUND)


def dump_data(driver, browser, ext_path):
    """Extract the objects Privacy Badger learned during its training run."""
    load_extension_page(driver, browser, ext_path, BACKGROUND)

    data = {}
    for obj in OBJECTS:
        script = 'return badger.storage.%s.getItemClones()' % obj
        data[obj] = driver.execute_script(script)
    return data


def size_of(data):
    """Get the size (in bytes) of the serialized data structure"""
    return len(json.dumps(data))


def timeout_workaround(driver):
    """
    Selenium has a bug where a tab that raises a timeout exception can't
    recover gracefully. So we kill the tab and make a new one.
    TODO: find actual bug ticket
    """
    driver.close()  # kill the broken site
    driver.switch_to_window(driver.window_handles.pop())
    before = set(driver.window_handles)
    driver.execute_script('window.open()')
    driver.switch_to_window((set(driver.window_handles) ^ before).pop())


def get_domain(driver, domain, wait_time):
    """
    Try to load a domain over https, and fall back to http if the initial load
    times out. Then sleep `wait_time` seconds on the site to wait for AJAX calls
    to complete.
    """
    try:
        url = "https://%s/" % domain
        driver.get(url)
    except TimeoutException:
        logger.info('timeout on %s ', url)
        timeout_workaround(driver)
        url = "http://%s/" % domain
        logger.info('trying %s', url)
        driver.get(url)

    time.sleep(wait_time)
    return url


def crawl(browser, out_path, ext_path, chromedriver_path, firefox_path, n_sites,
          timeout, wait_time, max_data_size, **kwargs):
    """
    Visit the top `n_sites` websites in the Majestic Million, in order, in a
    virtual browser with Privacy Badger installed. Afterwards, save the
    and snitch_map that the Badger learned.
    """
    domains = get_domain_list(n_sites, out_path)
    logger.info('starting new crawl with timeout %s n_sites %s',
                timeout, n_sites)

    # create an XVFB virtual display (to avoid opening an actual browser)
    vdisplay = Xvfb(width=1280, height=720)
    vdisplay.start()

    if browser == CHROME:
        driver = start_driver_chrome(ext_path, chromedriver_path)
    else:
        driver = start_driver_firefox(ext_path, firefox_path)

    driver.set_page_load_timeout(timeout)
    driver.set_script_timeout(timeout)

    def restart_browser(data):
        logger.info('restarting browser...')
        for _ in range(RETRIES):
            try:
                driver = start_driver_firefox(ext_path, firefox_path)
                load_user_data(driver, browser, ext_path, data)
                break
            except Exception as e:
                logger.error('Error restarting browser. Trying again...')
                logger.error('%s %s: %s', domain, type(e).__name__, e.msg)
        else:
            logger.error('Could not restart browser.')

        return driver

    # determine whether we need to restart the webdriver after an error
    def should_restart(e):
        return (type(e) == NoSuchWindowException or
            type(e) == SessionNotCreatedException or
            'response from marionette' in e.msg)

    # list of domains we actually visited
    visited = []
    last_data = None
    first_i = 0

    for i, domain in enumerate(domains):
        # If we can't load the options page for some reason, treat it like
        # any other error
        try:
            # save the state of privacy badger before we do anything else
            last_data = dump_data(driver, browser, ext_path)

            # If the localstorage data is getting too big, dump it and restart
            if size_of(last_data) > max_data_size:
                save(last_data, out_path, 'results-%d-%d.json' % (first_i, i))
                first_i = i + 1
                last_data = {}
                driver = restart_browser(last_data)

            logger.info('visiting %d: %s', i + 1, domain)
            url = get_domain(driver, domain, wait_time)
            visited.append(url)
        except TimeoutException:
            logger.info('timeout on %s ', domain)
            # TODO: how to get rid of this nested try?
            try:
                timeout_workaround(driver)
            except WebDriverException as e:
                if should_restart(e):
                    driver = restart_browser(last_data)
        except WebDriverException as e:
            logger.error('%s %s: %s', domain, type(e).__name__, e.msg)
            if should_restart(e):
                driver = restart_browser(last_data)
        except KeyboardInterrupt:
            logger.warn('Keyboard interrupt. Ending scan after %d sites.', i+1)
            break

    logger.info('Finished scan. Visited %d sites and errored on %d.',
                len(visited), i + 1 - len(visited))
    logger.info('Getting data from browser storage...')

    # If we can't load the background page here, there's a serious problem
    try:
        data = dump_data(driver, browser, ext_path)
    except Exception:
        if last_data:
            logger.error('Could not get badger storage. Using cached data...')
            data = last_data
        else:
            logger.error('Could not export data. Exiting.')
            sys.exit(1)

    driver.quit()
    vdisplay.stop()

    save(data, out_path, 'results-%d-%d.json' % (first_i, i))
    save(merge_saved_data(out_path), out_path)


def save(data, out_path, name='results.json'):
    data['version'] = version

    logger.info('Saving seed data version %s...', version)
    # save the snitch_map in a human-readable JSON file
    with open(os.path.join(out_path, name), 'w') as f:
        json.dump(data, f, indent=2, sort_keys=True, separators=(',', ': '))
    logger.info('Saved data to %s.', name)


def merge_saved_data(out_path):
    paths = glob.glob(os.path.join(out_path, 'results-*.json'))
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

    return {'version': version, 'snitch_map': snitch_map}


if __name__ == '__main__':
    args = ap.parse_args()

    # set up logging
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    log_fmt = logging.Formatter('%(asctime)s %(message)s')

    # by default, just log to file
    fh = logging.FileHandler(os.path.join(args.out_path, 'log.txt'))
    fh.setFormatter(log_fmt)
    logger.addHandler(fh)

    # log to stdout if configured
    if args.log_stdout:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(log_fmt)
        logger.addHandler(sh)

    # version is based on when the crawl started
    version = time.strftime('%Y.%-m.%-d', time.localtime())

    logger.info('Starting scan...')

    # the argparse arguments must match the function signature of crawl()
    crawl(**vars(args))

else:
    logger = logging.getLogger()
