#!/usr/bin/env python3

import configparser
import json
import os
import re
import sqlite3

from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from lib.basedomain import extract
from lib.mdfp import is_mdfp_first_party
from lib.utils import run


db_filename = "badger.sqlite3"
browsers = {
    "firefox": 1,
    "chrome": 2,
    "edge": 3
}
site_statuses = {
    "success": 1,
    "timeout": 2,
    "error": 3,
    "antibot": 4,
}
tracking_types = {}

re_patterns = {
    "log_ts": re.compile("[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2},[0-9]{3}"),
    "log_visiting": re.compile("[Vv]isiting [0-9]+: (.+)$"),
    "log_visited": re.compile("Visited ([^ ]+)(?: on (.+)$)"),
    "log_timeout": re.compile("Timed out loading ([^ ]+)(?: on (.+)|$)"),
    "log_error": re.compile("(?:Error loading|Exception on) ([^:]+):"),
    "log_restart": re.compile("[Rr]estarting browser( )?\\.\\.\\.")
}


def get_browser(log_txt):
    if " 'browserName': 'chrome',\n" in log_txt:
        return "chrome"
    if " 'browserName': 'firefox',\n" in log_txt:
        return "firefox"
    if "  browser: Edge\n" in log_txt:
        return "edge"
    if "  browser: chrome\n" in log_txt:
        return "chrome"
    if "  browser: firefox\n" in log_txt:
        return "firefox"
    if "\tbrowser: chrome" in log_txt:
        return "chrome"
    if " 'browserName': 'msedge',\n" in log_txt:
        return "edge"
    return None

# pylint: disable-next=too-many-arguments
def get_scan_id(cur, start_time, end_time, region, num_sites, browser, no_blocking, daily_scan):
    # TODO also record the list we're scanning against
    cur.execute("INSERT INTO scan (start_time, end_time, region, num_sites, "
                    "browser_id, no_blocking, daily_scan) "
                "VALUES (?,?,?,?,?,?,?)", (
                    start_time, end_time, region, num_sites,
                    browsers[browser], no_blocking, daily_scan))
    return cur.lastrowid

def create_tables(cur):
    cur.execute("DROP TABLE IF EXISTS browser")
    cur.execute("""
        CREATE TABLE browser (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(20) NOT NULL UNIQUE
        )""")
    for name, rowid in browsers.items():
        cur.execute("INSERT INTO browser (id,name) VALUES (?,?)", (rowid, name))

    cur.execute("DROP TABLE IF EXISTS scan")
    cur.execute("""
        CREATE TABLE scan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP NOT NULL,
            region VARCHAR(4) NOT NULL,
            num_sites INTEGER NOT NULL,
            browser_id INTEGER NOT NULL,
            no_blocking BOOLEAN NOT NULL CHECK (no_blocking IN (0, 1)),
            daily_scan BOOLEAN NOT NULL CHECK (daily_scan IN (0, 1)),
            FOREIGN KEY(browser_id) REFERENCES browser(id)
        )""")

    cur.execute("DROP TABLE IF EXISTS site")
    cur.execute("""
        CREATE TABLE site (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fqdn VARCHAR(200) NOT NULL UNIQUE
        )""")

    cur.execute("DROP TABLE IF EXISTS site_status")
    cur.execute("""
        CREATE TABLE site_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(20) NOT NULL UNIQUE
        )""")
    for name, rowid in site_statuses.items():
        cur.execute("INSERT INTO site_status (id,name) VALUES (?,?)", (rowid, name))

    cur.execute("DROP TABLE IF EXISTS scan_sites")
    cur.execute("""
        CREATE TABLE scan_sites (
            scan_id INTEGER NOT NULL,
            initial_site_id INTEGER NOT NULL,
            final_site_id INTEGER NOT NULL,
            status_id INTEGER NOT NULL,
            error_id INTEGER,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP NOT NULL,
            --UNIQUE(scan_id, initial_site_id)
            FOREIGN KEY(scan_id) REFERENCES scan(id),
            FOREIGN KEY(initial_site_id) REFERENCES site(id),
            FOREIGN KEY(final_site_id) REFERENCES site(id),
            FOREIGN KEY(status_id) REFERENCES site_status(id),
            FOREIGN KEY(error_id) REFERENCES error(id)
        )""")

    cur.execute("DROP TABLE IF EXISTS error")
    cur.execute("""
        CREATE TABLE error (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(200) NOT NULL UNIQUE
        )""")

    cur.execute("DROP TABLE IF EXISTS scan_crashes")
    cur.execute("""
        CREATE TABLE scan_crashes (
            scan_id INTEGER NOT NULL,
            error_id INTEGER NOT NULL,
            time TIMESTAMP NOT NULL,
            FOREIGN KEY(scan_id) REFERENCES scan(id),
            FOREIGN KEY(error_id) REFERENCES error(id)
        )""")

    cur.execute("DROP TABLE IF EXISTS tracker")
    cur.execute("""
        CREATE TABLE tracker (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            base VARCHAR(200) NOT NULL UNIQUE
        )""")

    cur.execute("DROP TABLE IF EXISTS tracking_type")
    cur.execute("""
        CREATE TABLE tracking_type (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(50) NOT NULL UNIQUE
        )""")

    cur.execute("DROP TABLE IF EXISTS tracking")
    # TODO add unique constraint?
    cur.execute("""
        CREATE TABLE tracking (
            scan_id INTEGER NOT NULL,
            site_id INTEGER NOT NULL,
            tracker_id INTEGER NOT NULL,
            tracking_type_id INTEGER,
            FOREIGN KEY(scan_id) REFERENCES scan(id),
            FOREIGN KEY(site_id) REFERENCES site(id),
            FOREIGN KEY(tracker_id) REFERENCES tracker(id),
            FOREIGN KEY(tracking_type_id) REFERENCES tracking_type(id)
        )""")

def get_id(cur, table, field, value):
    cur.execute(f"SELECT id FROM {table} WHERE {field} = ?", (value,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(f"INSERT INTO {table} ({field}) VALUES (?)", (value,))
    return cur.lastrowid

def get_error_string(line):
    error = None

    LEGACY_ERRORS = (
        "Failed to get current URL (NoSuchWindowException)",
        "Failed to switch windows (NoSuchWindowException)",
        "Failed to switch windows (InvalidArgumentException)",
        "Failed to switch windows (WebDriverException)",
        "Failed to switch windows (Browsing context has been discarded)",
        "Failed to switch windows (chrome not reachable", # sic
        "Timed out waiting for new window",
        "Failed to open new window (NoSuchWindowException)",
        "Failed to open new window with window.open()",
        "Failed to open new window",
        "Error closing timed out window (WebDriverException)",
        "Error closing timed out window (NoSuchWindowException)",
        "Error closing timed out window",
        "Closed all windows somehow",
        "Failed to get window handles (WebDriverException)",
        "Invalid session")

    if re_patterns["log_error"].search(line):
        error = line[24:].split(" ")[0]

        # add more context for some errors
        if error in ("WebDriverException", "NoSuchWindowException"):
            error = error + ":" + line[24:].partition(":")[2]
        elif error == "Error" and "driver.current_url is still" in line:
            error = error + ":" + line[24:].partition(":")[2]

        # normalize Firefox error page exceptions
        if "about:neterror?" in error:
            error_parts = error.partition("about:neterror?")
            error = error_parts[0] + error_parts[1] + error_parts[2].partition("&u=")[0]

    elif "Timed out loading extension page" in line:
        error = "Extension timeout"

    elif "Timed out loading skin/options.html" in line:
        error = "Extension timeout"

    elif re_patterns["log_timeout"].search(line):
        error = "Timeout"

    else:
        for err in LEGACY_ERRORS:
            if err in line:
                error = err
                break

    return error

def get_status_string(match_type, line, full_matching_string):
    status = "success"

    if match_type == 'log_timeout':
        status = "timeout"

    elif match_type == 'log_error':
        status = "error"

        # parse out antibot and errors that are actually timeouts
        error = line.partition(full_matching_string)[2].strip()
        if "security page" in error:
            status = "antibot"
        elif "e=netTimeout" in error:
            status = "timeout"

    return status

def ingest_log(cur, scan_id, log_txt):
    domain = None
    start_time = None
    prev_line = None

    for line in log_txt.split('\n'):
        if not re_patterns["log_ts"].match(line):
            continue

        if matches := re_patterns["log_visiting"].search(line):
            domain = matches.group(1)
            start_time = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
            prev_line = line
            continue

        if matches := re_patterns["log_restart"].search(line):
            error = get_error_string(prev_line)
            error_id = get_id(cur, "error", "name", error)
            cur.execute("""INSERT INTO scan_crashes
                (scan_id, error_id, time) VALUES (?,?,?)""", (
                    scan_id, error_id,
                    datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")))
            prev_line = line
            continue

        for match_type in ('log_visited', 'log_timeout', 'log_error'):
            if matches := re_patterns[match_type].search(line):
                if domain != matches.group(1):
                    break

                end_domain = domain
                if len(matches.groups()) > 1 and matches.group(2):
                    end_domain = urlparse(matches.group(2)).netloc
                    end_domain = extract(end_domain).registered_domain or end_domain

                end_time = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")

                status = get_status_string(match_type, line, matches.group(0))

                error_id = None
                if match_type == 'log_error':
                    error = get_error_string(line)
                    error_id = get_id(cur, "error", "name", error)

                cur.execute("""INSERT INTO scan_sites
                    (scan_id,
                    initial_site_id,
                    final_site_id,
                    status_id, error_id,
                    start_time, end_time)
                    VALUES (?,?,?,?,?,?,?)""", (
                        scan_id,
                        get_id(cur, "site", "fqdn", domain),
                        get_id(cur, "site", "fqdn", end_domain),
                        site_statuses[status], error_id,
                        start_time, end_time))

                break

        prev_line = line

def ingest_scan(cur, scan_id, snitch_map, tracking_map):
    for tracker_base, sites in snitch_map.items():
        tracker_id = get_id(cur, "tracker", "base", tracker_base)
        tracking_map_entry = tracking_map.get(tracker_base, {})

        for site in sites:
            # skip if latest MDFP says tracker_base and site are first parties
            if is_mdfp_first_party(site, tracker_base):
                continue

            site_id = get_id(cur, "site", "fqdn", site)

            for tracking_name in tracking_map_entry.get(site, [None]):
                if tracking_name and tracking_name not in tracking_types:
                    tracking_types[tracking_name] = get_id(
                        cur, "tracking_type", "name", tracking_name)

                cur.execute("""INSERT INTO tracking
                    (scan_id, tracker_id, site_id, tracking_type_id)
                    VALUES (?,?,?,?)""", (
                        scan_id, tracker_id, site_id,
                        tracking_types[tracking_name] if tracking_name else None))

# pylint: disable-next=too-many-locals
def ingest_distributed_scans(badger_swarm_dir, cur):
    bs_path = Path(badger_swarm_dir)
    if not bs_path.is_dir():
        print("Badger Swarm not found, skipping distributed scans")
        return

    scan_paths = sorted(
        [x for x in Path(bs_path/'output').iterdir() if x.is_dir()],
        # sort by date started
        key=lambda path: os.path.getctime(sorted(path.glob('*'), key=os.path.getctime)[0]))

    for scan_path in scan_paths:
        # skip if it's not clear this is a --no-blocking mode scan
        if not Path(scan_path/'results-noblocking.json').is_file():
            continue

        # skip if no run settings config
        config_path = Path(scan_path/'run_settings.ini')
        if not config_path.is_file():
            continue

        # skip non-default branch runs
        config = configparser.ConfigParser()
        config.read(config_path)
        run_settings = { key: val for name in config.keys() \
            for key, val in dict(config.items(name)).items() }
        if run_settings.get('pb_branch', 'master') not in ('master', 'mv3-chrome'):
            continue

        start_time = datetime.fromtimestamp(int(str(scan_path).rpartition('-')[-1]))

        results_glob = "results.???.json"
        log_glob = "log.???.txt"
        if not any(True for _ in scan_path.glob(results_glob)):
            results_glob = "results.????.json"
            log_glob = "log.????.txt"

        end_time = datetime.fromtimestamp(os.path.getmtime(
            sorted(scan_path.glob(results_glob), key=os.path.getmtime)[-1]))
        end_time = end_time.replace(microsecond=0)

        # skip if already ingested
        cur.execute("SELECT id FROM scan WHERE start_time = ? AND browser_id = ? "
                    "AND no_blocking = 1 AND daily_scan = 0",
                    (start_time, browsers[run_settings['browser']]))
        if cur.fetchone():
            continue

        scan_id = get_scan_id(cur, start_time, end_time,
                              run_settings['do_region'],
                              run_settings['num_sites'],
                              run_settings['browser'],
                              True, False)

        for log_file in scan_path.glob(log_glob):
            ingest_log(cur, scan_id, log_file.read_text())

        for results_file in scan_path.glob(results_glob):
            results = json.loads(results_file.read_bytes())
            ingest_scan(cur, scan_id, results['snitch_map'],
                        results.get('tracking_map', {}))

def ingest_daily_scans(cur):
    revisions = run("git rev-list HEAD -- log.txt".split(" "))
    if not revisions:
        return

    for rev in revisions.split('\n'):
        log_txt = log_txt_full = run(f"git show {rev}:log.txt".split(" "))

        end_time = datetime.strptime(
                log_txt[log_txt.rindex("\n")+1:][:19], "%Y-%m-%d %H:%M:%S")

        # discard most of the log
        log_txt = log_txt[:log_txt.index("isiting 1:")]

        num_sites_idx = log_txt.index("domains to crawl: ")
        num_sites = log_txt[num_sites_idx+18:log_txt.index("\n", num_sites_idx)]

        browser = get_browser(log_txt)
        if browser not in browsers:
            print(f"Skipping scan {rev}: unrecognized browser {browser}")
            continue

        # skip non-default branch runs
        branch_info_idx = log_txt.find("  Badger branch: ")
        if branch_info_idx > -1:
            branch = log_txt[branch_info_idx+17 : log_txt.index("\n", branch_info_idx+17)]
            if branch not in ("master", "mv3-chrome"):
                continue

        start_time = datetime.strptime(log_txt[:19], "%Y-%m-%d %H:%M:%S")

        no_blocking = False
        if "  blocking: off\n" in log_txt:
            no_blocking = True

        # as scans are ordered from most recent to least,
        # short-circuit upon encountering an already ingested scan
        cur.execute("SELECT id FROM scan WHERE start_time = ? AND browser_id = ? "
                    "AND no_blocking = ? AND daily_scan = 1",
                    (start_time, browsers[browser], no_blocking))
        if cur.fetchone():
            return

        scan_id = get_scan_id(cur, start_time, end_time, "sfo1", num_sites,
                              browser, no_blocking, True)

        ingest_log(cur, scan_id, log_txt_full)

        results = json.loads(run(f"git show {rev}:results.json".split(" ")))

        ingest_scan(cur, scan_id, results['snitch_map'],
                    results.get('tracking_map', {}))


if __name__ == '__main__':
    num_scans = 0
    rebuild = True
    if Path(db_filename).is_file():
        rebuild = input(f"Rebuild {db_filename}? (y/N) ") == "y"

    with sqlite3.connect(db_filename, detect_types=sqlite3.PARSE_DECLTYPES) as db:
        cur = db.cursor()

        if rebuild:
            print("Rebuilding...")
            create_tables(cur)
        else:
            cur.execute("SELECT COUNT(*) FROM scan")
            num_scans = int(cur.fetchone()[0])

        print("Ingesting distributed scans...")
        # TODO don't hardcode
        ingest_distributed_scans("../badger-swarm", cur)

        print("Ingesting daily scans...")
        ingest_daily_scans(cur)

        cur.execute("SELECT COUNT(*) FROM scan")
        print(f"{'Rebuilt' if rebuild else 'Updated'} {db_filename} with data "
              f"from {int(cur.fetchone()[0]) - num_scans} scans")

        # TODO generate prevalence data for validate.py

        print("All done")
