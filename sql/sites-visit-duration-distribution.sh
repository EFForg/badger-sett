#!/usr/bin/env bash

sqlite3 badger.sqlite3 -batch -header "SELECT
    (CAST(STRFTIME('%s', scan_sites.end_time) AS INTEGER) -
      CAST(STRFTIME('%s', scan_sites.start_time) AS INTEGER)) AS visit_duration,
    CASE WHEN scan_sites.status_id = 1 THEN '-' ELSE site_status.name END AS status,
    browser.name AS browser,
    CASE WHEN scan.no_blocking = 1 THEN 'noblocking' ELSE 'standard' END AS 'scan type',
    COUNT(*) num
  FROM scan_sites
  JOIN scan ON scan.id = scan_sites.scan_id
  JOIN site_status ON site_status.id = scan_sites.status_id
  JOIN browser ON browser.id = scan.browser_id
  WHERE scan.start_time > DATETIME('now', '-30 day')
  GROUP BY browser.id, scan.no_blocking, site_status.name, visit_duration
  ORDER BY visit_duration ASC, num DESC" | column -s '|' -t
