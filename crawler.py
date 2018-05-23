#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
# adapted from https://github.com/cowlicks/badger-claw
import argparse
from glob import glob
import hashlib
import json
import logging
import os
import struct
import string
import sys
from time import sleep, time
from urllib.request import urlopen

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from xvfbwrapper import Xvfb


# we'll do the test with chrome
BG_URL_FMT = 'chrome-extension://%s/_generated_background_page.html'
OBJECTS = ['action_map', 'snitch_map']
CHROMEDRIVER_PATH='/usr/bin/chromedriver'
MAJESTIC_URL = "http://downloads.majesticseo.com/majestic_million.csv"
WEEK_IN_SECONDS = 604800

ap = argparse.ArgumentParser()
ap.add_argument('--out-path', default='./',
                help='Path at which to save output')
ap.add_argument('--ext-path', default='privacy-badger.crx',
                help='Path to the Privacy Badger extension binary')
ap.add_argument('--chromedriver-path', default=CHROMEDRIVER_PATH,
                help='Path to the Privacy Badger extension binary')
ap.add_argument('--n-sites', type=int, default=10000,
                help='Number of websites to visit on the crawl')
ap.add_argument('--timeout', type=float, default=10,
                help='Amount of time to allow each site to load, in seconds')
ap.add_argument('--wait-time', type=float, default=5,
                help='Amount of time to wait on each site after it loads, in seconds')
ap.add_argument('--log-stdout', action='store_true', default=False,
                help='If set, log to stdout as well as log.txt')


def get_pub_key_from_crx(crx_file):
    with open(crx_file, 'rb') as f:
        data = f.read()
    header = struct.unpack('<4sIII', data[:16])
    pubkey = struct.unpack('<%ds' % header[2], data[16:16+header[2]])[0]
    return pubkey


def get_extension_id(crx_file):
    pubkey = get_pub_key_from_crx(crx_file)
    digest = hashlib.sha256(pubkey).hexdigest()

    trans = str.maketrans('0123456789abcdef', string.ascii_lowercase[:16])
    return str.translate(digest[:32], trans)


def get_domain_list(n_sites):
    """Load the top million domains from disk or the web"""
    domains = []

    top_1m_file = os.path.join(args.out_path, MAJESTIC_URL.split('/')[-1])

    # download the file if it doesn't exist or if it's more than a week stale
    if (not os.path.exists(top_1m_file) or
        time() - os.path.getmtime(top_1m_file) > WEEK_IN_SECONDS):
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


def start_driver(ext_path, chromedriver_path):
    """Start a new Selenium web driver and install the bundled extension."""
    opts = Options()
    opts.add_extension(ext_path)
    opts.add_experimental_option("prefs", {"profile.block_third_party_cookies": False})
    opts.add_argument('--dns-prefetch-disable')
    return webdriver.Chrome(chromedriver_path, chrome_options=opts)


def dump_data(driver):
    """Extract the objects Privacy Badger learned during its training run."""
    driver.get(BG_URL_FMT % get_extension_id(args.ext_path))
    data = {}
    for obj in OBJECTS:
        script = 'return badger.storage.%s.getItemClones()' % obj
        data[obj] = driver.execute_script(script)
    return data


def timeout_workaround(driver):
    """
    Selenium has a bug where a tab that raises a timeout exception can't
    recover gracefully. So we kill the tab and make a new one.
    """
    driver.close()  # kill the broken site
    driver.switch_to_window(driver.window_handles.pop())
    before = set(driver.window_handles)
    driver.execute_script('window.open()')
    driver.switch_to_window((set(driver.window_handles) ^ before).pop())
    return driver


def get_domain(driver, domain, wait_time):
    """
    Try to load a domain over https, and fall back to http if the initial load
    fails. Then sleep `wait_time` seconds on the site to wait for AJAX calls to
    complete.
    """
    try:
        url = "https://%s/" % domain
        driver.get(url)
    except WebDriverException:
        url = "http://%s/" % domain
        driver.get(url)
    sleep(wait_time)


def crawl(ext_path, chromedriver_path, n_sites, timeout, wait_time, **kwargs):
    """
    Visit the top `n_sites` websites in the Majestic Million, in order, in a
    virtual browser with Privacy Badger installed. Afterwards, save the
    action_map and snitch_map that the Badger learned.
    """
    domains = get_domain_list(n_sites)
    logger.info('starting new crawl with timeout %s n_sites %s' %
                (timeout, n_sites))

    # create an XVFB virtual display (to avoid opening an actual browser)
    vdisplay = Xvfb(width=1280, height=720)
    vdisplay.start()

    driver = start_driver(ext_path, chromedriver_path)
    driver.set_page_load_timeout(timeout)
    driver.set_script_timeout(timeout)

    for domain in domains:
        logger.info('visiting %s' % domain)
        try:
            get_domain(driver, domain, wait_time)
        except TimeoutException:
            logger.info('timeout on %s ' % domain)
            driver = timeout_workaround(driver)
            continue

    data = dump_data(driver)
    driver.quit()
    vdisplay.stop()

    return data


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

    # the names of the argparse arguments must match the function signature of
    # crawl()
    results = crawl(**vars(args))

    # save the action_map and snitch_map in a human-readable Json file
    with open(os.path.join(args.out_path, 'results.json'), 'w') as f:
        json.dump(results, f, indent=2, sort_keys=True)
