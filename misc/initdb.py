#!/usr/bin/env python3

import datetime
import json
import pathlib
import re
import sqlite3
import subprocess


browsers = {
    "firefox": 1,
    "chrome": 2,
    "edge": 3
}


def run(cmd, cwd=pathlib.Path(__file__).parent.parent.resolve()):
    """Convenience wrapper for getting the output of CLI commands"""
    return subprocess.run(cmd, capture_output=True, check=False,
                          cwd=cwd, text=True).stdout.strip()

def get_browser_from_commit(rev, version):
    """Returns the browser string for daily scans with corresponding logs;
    returns None otherwise."""

    subject = run(f"git show {rev} -s --format=%s".split(" "))
    version_esc = version.replace('.', '\\.')

    if matches := re.search(f"^Add data {version_esc} " + r"\(master ([^ \)]+)", subject):
        return matches.group(1)

    if matches := re.search(f"^Add data v{version_esc} from (.+)$", subject):
        return matches.group(1)

    if subject == f"Update seed data: {version}":
        log_txt = run(f"git show {rev}:log.txt".split(" "))
        if not log_txt:
            return None
        if "'browserName': 'chrome'," in log_txt or "browser: chrome" in log_txt:
            return "chrome"
        if "'browserName': 'firefox'," in log_txt or "browser: firefox" in log_txt:
            return "firefox"

    return None

def create_tables(cur):
    cur.execute("DROP TABLE IF EXISTS browser")
    cur.execute("""
        CREATE TABLE browser (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(20) NOT NULL UNIQUE
        )""")

    for name, rowid in browsers.items():
        cur.execute("INSERT INTO browser (id,name) VALUES (?,?)", (rowid, name))

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

    cur.execute("DROP TABLE IF EXISTS tracking")
    # TODO add unique constraint?
    cur.execute("""
        CREATE TABLE tracking (
            scan_date TIMESTAMP NOT NULL,
            browser_id INTEGER,
            site_id INTEGER,
            tracker_id INTEGER,
            FOREIGN KEY(browser_id) REFERENCES browser(id)
            FOREIGN KEY(site_id) REFERENCES site(id)
            FOREIGN KEY(tracker_id) REFERENCES tracker(id)
        )""")

def get_id(cur, table, field, value):
    cur.execute(f"SELECT id FROM {table} WHERE {field} = ?", (value,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(f"INSERT INTO {table} ({field}) VALUES (?)", (value,))
    return cur.lastrowid

def print_summary(cur):
    cur.execute("SELECT COUNT(DISTINCT scan_date) from TRACKING")
    print(f"Rebuilt badger.sqlite3 with data from {cur.fetchone()[0]} scans")

    print("\nThe most prevalent third-party tracking domains:")
    cur.execute("""
        SELECT t.base, COUNT(distinct tr.site_id) AS num_sites
        FROM tracking tr
        JOIN tracker t ON t.id = tr.tracker_id
        --WHERE scan_date > DATETIME('now', '-30 day')
        GROUP BY t.base
        ORDER BY num_sites  DESC
        LIMIT 40""")
    top_prevalence = None
    for row in cur.fetchall():
        if not top_prevalence:
            top_prevalence = row[1]
        print(" ", round(row[1] / top_prevalence, 1), row[0])
    print()

def main():
    revisions = run("git rev-list HEAD -- results.json".split(" "))
    if not revisions:
        return

    with sqlite3.connect("badger.sqlite3", detect_types=sqlite3.PARSE_DECLTYPES) as db:
        cur = db.cursor()
        create_tables(cur)

        for rev in revisions.split('\n'):
            results = json.loads(run(f"git show {rev}:results.json".split(" ")))

            version = results.get('version')
            if not version:
                continue

            browser = get_browser_from_commit(rev, version)
            if not browser:
                continue

            year, month, day = (int(x) for x in version.split("."))
            #tracking_map = results.get('tracking_map', {})

            for tracker_base, sites in results['snitch_map'].items():
                for site in sites:
                    # TODO do something with tracking_map / canvas, beacon, etc.
                    #tracking_types = tracking_map.get(tracker_base, {}).get(site, [])
                    # TODO don't store if latest MDFP says tracker_base and site are actually first parties
                    tracker_id = get_id(cur, "tracker", "base", tracker_base)
                    site_id = get_id(cur, "site", "fqdn", site)
                    cur.execute("INSERT INTO tracking "
                        "(scan_date, browser_id, tracker_id, site_id) "
                        "VALUES (?,?,?,?)", (
                            datetime.datetime(year=year, month=month, day=day),
                            browsers[browser], tracker_id, site_id))

        print_summary(cur)
        # TODO generate prevalence data for validate.py
        print("All done")


if __name__ == '__main__':
    main()
