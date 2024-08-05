#!/usr/bin/env python3

import configparser
import datetime
import json
import os
import pathlib
import re
import sqlite3
import subprocess


browsers = {
    "firefox": 1,
    "chrome": 2,
    "edge": 3
}
tracking_types = {}


def run(cmd, cwd=pathlib.Path(__file__).parent.parent.resolve()):
    """Convenience wrapper for getting the output of CLI commands"""
    res = subprocess.run(
            cmd, cwd=cwd, capture_output=True, check=True, text=True)

    return res.stdout.strip()

def get_browser_from_commit(rev, version):
    """Returns the browser string for daily scans with corresponding logs;
    returns None otherwise."""

    subject = run(f"git show {rev} -s --format=%s".split(" "))
    version_esc = version.replace('.', '\\.')

    # skip non-default branch runs
    if matches := re.search(f"^Add data {version_esc} " + r"\((?:master|mv3-chrome) ([^ \)]+)", subject):
        return matches.group(1)

    if matches := re.search(f"^Add data v{version_esc} from (.+)$", subject):
        return matches.group(1)

    if subject == f"Update seed data: {version}":
        try:
            log_txt = run(f"git show {rev}:log.txt".split(" "))
        except subprocess.CalledProcessError:
            return None
        if "'browserName': 'chrome'," in log_txt or "browser: chrome" in log_txt:
            return "chrome"
        if "'browserName': 'firefox'," in log_txt or "browser: firefox" in log_txt:
            return "firefox"

    return None

def get_scan_id(cur, version, browser, no_blocking):
    year, month, day = (int(x) for x in version.split("."))
    cur.execute("INSERT INTO scan (date, browser_id, no_blocking) "
                "VALUES (?,?,?)", (
                    datetime.datetime(year=year, month=month, day=day),
                    browsers[browser],
                    no_blocking))
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

def ingest_scan(cur, mdfp, scan_id, snitch_map, tracking_map):
    for tracker_base, sites in snitch_map.items():
        tracker_id = get_id(cur, "tracker", "base", tracker_base)
        tracking_map_entry = tracking_map.get(tracker_base, {})

        for site in sites:
            # skip if latest MDFP says tracker_base and site are first parties
            if site in mdfp.get(tracker_base, []):
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

def print_summary(cur):
    cur.execute("SELECT COUNT(*) FROM scan")
    print(f"Rebuilt badger.sqlite3 with data from {cur.fetchone()[0]} scans")

    print("\nThe most prevalent (appearing on the greatest number of distinct"
        "\nwebsites) third-party tracking domains over the last 365 days:\n")
    cur.execute("""
        SELECT t.base, COUNT(distinct tr.site_id) AS num_sites
        FROM tracking tr
        JOIN scan ON scan.id = tr.scan_id
        JOIN tracker t ON t.id = tr.tracker_id
        WHERE scan.date > DATETIME('now', '-365 day')
        GROUP BY t.base
        ORDER BY num_sites DESC
        LIMIT 40""")
    top_prevalence = None
    for row in cur.fetchall():
        if not top_prevalence:
            top_prevalence = row[1]
        print(f"  {round(row[1] / top_prevalence, 2):.2f}  {row[0]}")

    print("\nThe most prevalent canvas fingerprinters over same date range:\n")
    cur.execute("""
        SELECT t.base, COUNT(distinct tr.site_id) AS num_sites
        FROM tracking tr
        JOIN scan ON scan.id = tr.scan_id
        JOIN tracker t ON t.id = tr.tracker_id
        JOIN tracking_type tt ON tt.id = tr.tracking_type_id
        WHERE tt.name = 'canvas' AND scan.date > DATETIME('now', '-365 day')
        GROUP BY t.base
        ORDER BY num_sites DESC
        LIMIT 20""")
    for row in cur.fetchall():
        print(f"  {round(row[1] / top_prevalence, 2):.2f}  {row[0]}")
    print()

def load_mdfp(pb_dir):
    mdfp_array = None
    try:
        mdfp_export_js = f"""
const {{ default: mdfp }} = await import('{pb_dir}/src/js/multiDomainFirstParties.js');
process.stdout.write(JSON.stringify(mdfp.multiDomainFirstPartiesArray));"""
        mdfp_array = run(["node", "--experimental-default-type=module",
                          f'--eval={mdfp_export_js}'])
    except subprocess.CalledProcessError as ex:
        print(ex.stderr)

    if not mdfp_array:
        print("Failed to load MDFP definitions")
        return {}

    mdfp_lookup_dict = {}
    for entity_bases in json.loads(mdfp_array):
        for base in entity_bases:
            mdfp_lookup_dict[base] = entity_bases
    return mdfp_lookup_dict

def ingest_distributed_scans(badger_swarm_dir, cur, mdfp):
    bs_path = pathlib.Path(badger_swarm_dir)
    if not bs_path.is_dir():
        print("Badger Swarm not found, skipping distributed scans")
        return

    scan_paths = sorted(
        [x for x in pathlib.Path(bs_path/'output').iterdir() if x.is_dir()],
        # sort by date started
        key=lambda path: os.path.getctime(sorted(path.glob('*'), key=os.path.getctime)[0]))

    for scan_path in scan_paths:
        # skip if it's not clear this is a --no-blocking mode scan
        if not pathlib.Path(scan_path/'results-noblocking.json').is_file():
            continue

        # skip if no run settings config
        config_path = pathlib.Path(scan_path/'run_settings.ini')
        if not config_path.is_file():
            continue

        # skip non-default branch runs
        config = configparser.ConfigParser()
        config.read(config_path)
        run_settings = { key: val for name in config.keys() \
            for key, val in dict(config.items(name)).items() }
        if run_settings.get('pb_branch', 'master') not in ('master', 'mv3-chrome'):
            continue

        browser = run_settings['browser']

        results_glob = "results.???.json"
        if not any(True for _ in scan_path.glob(results_glob)):
            results_glob = "results.????.json"

        for results_file in scan_path.glob(results_glob):
            results = json.loads(results_file.read_bytes())
            version = results['version']
            scan_id = get_scan_id(cur, version, browser, True)
            ingest_scan(cur, mdfp, scan_id, results['snitch_map'],
                        results.get('tracking_map', {}))

def ingest_daily_scans(cur, mdfp):
    revisions = run("git rev-list HEAD -- results.json".split(" "))
    if not revisions:
        return

    for rev in revisions.split('\n'):
        results = json.loads(run(f"git show {rev}:results.json".split(" ")))

        version = results.get('version')
        if not version:
            continue

        browser = get_browser_from_commit(rev, version)
        if not browser:
            continue
        if browser not in browsers:
            print(f"Skipping scan version {version}: unrecognized browser {browser}")
            continue

        scan_id = get_scan_id(cur, version, browser, False)

        ingest_scan(cur, mdfp, scan_id, results['snitch_map'],
                    results.get('tracking_map', {}))


if __name__ == '__main__':
    # TODO don't hardcode
    mdfp = load_mdfp("../privacybadger")

    with sqlite3.connect("badger.sqlite3", detect_types=sqlite3.PARSE_DECLTYPES) as db:
        cur = db.cursor()

        create_tables(cur)

        # TODO don't hardcode
        ingest_distributed_scans("../badger-swarm", cur, mdfp)

        ingest_daily_scans(cur, mdfp)

        print_summary(cur)
        # TODO generate prevalence data for validate.py
        print("All done")
