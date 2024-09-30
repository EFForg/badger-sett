#!/usr/bin/env python3

import configparser
import datetime
import json
import os
import sqlite3
import subprocess

from pathlib import Path

from lib.mdfp import is_mdfp_first_party
from lib.utils import run


db_filename = "badger.sqlite3"
browsers = {
    "firefox": 1,
    "chrome": 2,
    "edge": 3
}
tracking_types = {}


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

def get_scan_id(cur, scan_time, browser, no_blocking, daily_scan):
    # TODO also record region we're scanning from
    # TODO and the list we're scanning against
    cur.execute("INSERT INTO scan (date, browser_id, no_blocking, daily_scan) "
                "VALUES (?,?,?,?)", (scan_time, browsers[browser], no_blocking,
                daily_scan))
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
            date TIMESTAMP NOT NULL,
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
            FOREIGN KEY(scan_id) REFERENCES scan(id)
            FOREIGN KEY(site_id) REFERENCES site(id)
            FOREIGN KEY(tracker_id) REFERENCES tracker(id)
            FOREIGN KEY(tracking_type_id) REFERENCES tracking_type(id)
        )""")

def get_id(cur, table, field, value):
    cur.execute(f"SELECT id FROM {table} WHERE {field} = ?", (value,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(f"INSERT INTO {table} ({field}) VALUES (?)", (value,))
    return cur.lastrowid

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

        scan_time = datetime.datetime.fromtimestamp(
                int(str(scan_path).rpartition('-')[-1]))

        browser = run_settings['browser']

        # skip if already ingested
        cur.execute("SELECT id FROM scan WHERE date = ? AND browser_id = ? "
                    "AND no_blocking = 1 AND daily_scan = 0",
                    (scan_time, browsers[browser]))
        if cur.fetchone():
            continue

        scan_id = get_scan_id(cur, scan_time, browser, True, False)

        results_glob = "results.???.json"
        if not any(True for _ in scan_path.glob(results_glob)):
            results_glob = "results.????.json"

        for results_file in scan_path.glob(results_glob):
            results = json.loads(results_file.read_bytes())
            ingest_scan(cur, scan_id, results['snitch_map'],
                        results.get('tracking_map', {}))

def ingest_daily_scans(cur):
    revisions = run("git rev-list HEAD -- results.json".split(" "))
    if not revisions:
        return

    for rev in revisions.split('\n'):
        log_txt = None

        try:
            log_txt = run(f"git show {rev}:log.txt".split(" "))
        except subprocess.CalledProcessError:
            continue

        # discard most of the log
        log_txt = log_txt[:log_txt.index("isiting 1:")]

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

        scan_time = datetime.datetime.strptime(log_txt[:19], "%Y-%m-%d %H:%M:%S")

        no_blocking = False
        if "  blocking: off\n" in log_txt:
            no_blocking = True

        # as scans are ordered from most recent to least,
        # short-circuit upon encountering an already ingested scan
        cur.execute("SELECT id FROM scan WHERE date = ? AND browser_id = ? "
                    "AND no_blocking = ? AND daily_scan = 1",
                    (scan_time, browsers[browser], no_blocking))
        if cur.fetchone():
            return

        scan_id = get_scan_id(cur, scan_time, browser, no_blocking, True)

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
