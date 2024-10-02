#!/usr/bin/env bash

sqlite3 badger.sqlite3 -batch -header -column "SELECT start_time, end_time,
    ((CAST(STRFTIME('%s', end_time) AS INT) - CAST(STRFTIME('%s', start_time) AS INT)) / 60 / 60) AS num_hours,
    browser.name AS browser,
    no_blocking,
    num_sites,
    COUNT(DISTINCT blocked_trackers.tracker_id) AS num_blocked
  FROM scan
  JOIN browser ON browser.id = scan.browser_id
  JOIN (SELECT scan.id AS scan_id,
      tr.tracker_id
    FROM scan
    JOIN browser ON browser.id = scan.browser_id
    JOIN tracking tr ON tr.scan_id = scan.id
    WHERE scan.daily_scan = 1
      AND scan.start_time > DATETIME('now', '-30 day')
    GROUP BY tr.scan_id, tr.tracker_id
    HAVING COUNT(DISTINCT tr.site_id) > 2)
      AS blocked_trackers ON blocked_trackers.scan_id = scan.id
  WHERE scan.daily_scan = 1
    AND scan.start_time > DATETIME('now', '-30 day')
  GROUP BY scan_id
  ORDER BY scan.start_time DESC"
