#!/usr/bin/env python3

import sqlite3


def print_prevalence_summary(cur):
    cur.execute("""
        SELECT COUNT(DISTINCT initial_site_id)
        FROM scan_sites
        JOIN scan ON scan.id = scan_id
        WHERE scan.no_blocking = 1 AND scan.daily_scan = 1
            AND scan.start_time > DATETIME('now', '-365 day')""")
    total_sites = cur.fetchone()[0]

    print("\nThe most prevalent (seen tracking on the greatest number of websites)"
        "\nthird-party tracking domains over the last 365 days:\n")
    cur.execute("""
        SELECT t.base, COUNT(DISTINCT tr.site_id) AS num_sites
        FROM tracking tr
        JOIN scan ON scan.id = tr.scan_id
        JOIN tracker t ON t.id = tr.tracker_id
        WHERE scan.no_blocking = 1 AND scan.daily_scan = 1
            AND scan.start_time > DATETIME('now', '-365 day')
        GROUP BY t.base
        ORDER BY num_sites DESC
        LIMIT 40""")
    top_prevalence = None
    col_width = None
    for row in cur.fetchall():
        if not top_prevalence:
            top_prevalence = row[1]
            col_width = len(str(top_prevalence))
        # total site count, site count for tracking domain
        print(f"  {total_sites}  {row[1]:>{col_width}}  "
            # absolute prevalence
            f"{round(row[1] / total_sites, 2):.2f}  "
            # relative prevalence, tracking domain
            f"{round(row[1] / top_prevalence, 2):.2f}  {row[0]}")

    print("\nThe most prevalent canvas fingerprinters over same date range:\n")
    cur.execute("""
        SELECT t.base, COUNT(DISTINCT tr.site_id) AS num_sites
        FROM tracking tr
        JOIN scan ON scan.id = tr.scan_id
        JOIN tracker t ON t.id = tr.tracker_id
        JOIN tracking_type tt ON tt.id = tr.tracking_type_id
        WHERE scan.no_blocking = 1 AND scan.daily_scan = 1
            AND tt.name = 'canvas' AND scan.start_time > DATETIME('now', '-365 day')
        GROUP BY t.base
        ORDER BY num_sites DESC
        LIMIT 20""")
    for row in cur.fetchall():
        print(f"  {total_sites}  {row[1]:>{col_width}}  "
            f"{round(row[1] / total_sites, 2):.2f}  "
            f"{round(row[1] / top_prevalence, 2):.2f}  {row[0]}")
    print()


if __name__ == "__main__":
    with sqlite3.connect("badger.sqlite3", detect_types=sqlite3.PARSE_DECLTYPES) as db:
        cur = db.cursor()
        print_prevalence_summary(cur)
