#!/usr/bin/env python3

import sqlite3


def print_trends(cur):
    # the date ranges
    date_prev = "60 day"
    date_curr = "30 day"

    cur.execute(f"""
        SELECT COUNT(DISTINCT tr.site_id),
            COUNT(DISTINCT tr.scan_id)
        FROM tracking tr
        JOIN site ON site.id = tr.site_id
        JOIN scan ON scan.id = tr.scan_id
        WHERE scan.no_blocking = 1 AND scan.daily_scan = 1
            AND scan.start_time >= DATETIME('now', '-{date_prev}')
            AND scan.start_time < DATETIME('now', '-{date_curr}')""")
    total_sites_prev, total_scans_prev = cur.fetchone()

    cur.execute(f"""
        SELECT t.base, COUNT(DISTINCT tr.site_id) AS num_sites
        FROM tracking tr
        JOIN scan ON scan.id = tr.scan_id
        JOIN tracker t ON t.id = tr.tracker_id
        WHERE scan.no_blocking = 1 AND scan.daily_scan = 1
            AND scan.start_time >= DATETIME('now', '-{date_prev}')
            AND scan.start_time < DATETIME('now', '-{date_curr}')
        GROUP BY t.base
        ORDER BY num_sites DESC""")

    prev = { row[0]: row[1] for row in cur.fetchall() }
    if not prev:
        print("Not enough past data for selected date range")
        return
    top_prevalence_prev = next(iter(prev.values()))

    cur.execute(f"""
        SELECT COUNT(DISTINCT tr.site_id),
            COUNT(DISTINCT tr.scan_id)
        FROM tracking tr
        JOIN site ON site.id = tr.site_id
        JOIN scan ON scan.id = tr.scan_id
        WHERE scan.no_blocking = 1 AND scan.daily_scan = 1
            AND scan.start_time >= DATETIME('now', '-{date_curr}')""")
    total_sites, total_scans = cur.fetchone()

    cur.execute(f"""
        SELECT t.base, COUNT(DISTINCT tr.site_id) AS num_sites
        FROM tracking tr
        JOIN scan ON scan.id = tr.scan_id
        JOIN tracker t ON t.id = tr.tracker_id
        WHERE scan.no_blocking = 1 AND scan.daily_scan = 1
            AND scan.start_time >= DATETIME('now', '-{date_curr}')
        GROUP BY t.base
        ORDER BY num_sites DESC""")

    top_prevalence = None

    for row in cur.fetchall():
        if not top_prevalence:
            top_prevalence = row[1]

            print(f"Comparing {total_scans_prev} scans to {total_scans} scans")

            # absolute change in total sites
            print("\nSite totals:")
            print(total_sites_prev)
            print(total_sites, f"({round((total_sites - total_sites_prev) / total_sites_prev * 100, 2)}%)")

            # absolute change in most prevalent domain
            print("\nMost prevalent tracker:")
            print(next(iter(prev.keys())), top_prevalence_prev)
            print(f"{row[0]} {top_prevalence} ({round((top_prevalence - top_prevalence_prev) / top_prevalence_prev * 100, 2)}%)\n")

            print("Notable changes in relative tracker prevalence:")

        rel_prevalence = row[1] / top_prevalence

        if rel_prevalence < 0.01:
            continue

        delta = 1.0
        prevalence_prev = prev.get(row[0], None)
        if prevalence_prev:
            rel_prevalence_prev = prevalence_prev / top_prevalence_prev
            delta = rel_prevalence - rel_prevalence_prev

        if abs(delta) < 0.04:
            continue

        print("  "
            # num sites (previous)
            f"{prevalence_prev if prevalence_prev else 0:>4}  "
            # num sites
            f"{row[1]:>4}  "
            # relative prevalence
            f"{round(rel_prevalence, 2):.2f}  "
            # change from previous
            f"{round(delta, 2) * 100:>3.0f}%  "
            # tracking domain
            f"{row[0]}")


if __name__ == "__main__":
    with sqlite3.connect("badger.sqlite3", detect_types=sqlite3.PARSE_DECLTYPES) as db:
        cur = db.cursor()
        print_trends(cur)
