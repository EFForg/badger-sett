#!/usr/bin/env python3

import sqlite3


def print_trends(cur):
    cur.execute("""
        SELECT t.base, COUNT(DISTINCT tr.site_id) AS num_sites
        FROM tracking tr
        JOIN scan ON scan.id = tr.scan_id
        JOIN tracker t ON t.id = tr.tracker_id
        WHERE scan.no_blocking = 1 AND scan.daily_scan = 1
            AND scan.date >= DATETIME('now', '-14 day')
            AND scan.date < DATETIME('now', '-7 day')
        GROUP BY t.base
        ORDER BY num_sites DESC""")

    prev = { row[0]: row[1] for row in cur.fetchall() }
    if not prev:
        print("Not enough past data for selected date range")
        return
    top_prevalence_prev = next(iter(prev.values()))

    cur.execute("""
        SELECT t.base, COUNT(DISTINCT tr.site_id) AS num_sites
        FROM tracking tr
        JOIN scan ON scan.id = tr.scan_id
        JOIN tracker t ON t.id = tr.tracker_id
        WHERE scan.no_blocking = 1 AND scan.daily_scan = 1
            AND scan.date >= DATETIME('now', '-7 day')
        GROUP BY t.base
        ORDER BY num_sites DESC""")

    top_prevalence = None

    for row in cur.fetchall():
        if not top_prevalence:
            top_prevalence = row[1]

        rel_prevalence = row[1] / top_prevalence

        if rel_prevalence < 0.01:
            continue

        delta = 1.0
        prevalence_prev = prev.get(row[0], None)
        if prevalence_prev:
            rel_prevalence_prev = prevalence_prev / top_prevalence_prev
            delta = rel_prevalence - rel_prevalence_prev

        if abs(delta) < 0.03:
            continue

        print("  "
            # num sites
            f"{row[1]:>{len(str(top_prevalence))}}  "
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
