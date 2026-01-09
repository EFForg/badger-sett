#!/usr/bin/env bash

sqlite3 badger.sqlite3 -batch -header "SELECT browser.name AS browser,
    scan.region,
    scan_sites.start_time AS visit_start,
    CASE WHEN scan_sites.status_id = 1 THEN '-' ELSE site_status.name END AS status,
    start_site.fqdn AS initial_site_fqdn,
    CASE WHEN end_site.fqdn = start_site.fqdn THEN '-' ELSE end_site.fqdn END AS final_site_fqdn,
    (CAST(STRFTIME('%s', scan_sites.end_time) AS INTEGER) -
      CAST(STRFTIME('%s', scan_sites.start_time) AS INTEGER)) AS visit_duration
  FROM scan_sites
  JOIN site AS start_site ON start_site.id = scan_sites.initial_site_id
  JOIN site AS end_site ON end_site.id = scan_sites.final_site_id
  JOIN site_status ON site_status.id = scan_sites.status_id
  JOIN scan ON scan.id = scan_sites.scan_id
  JOIN browser ON browser.id = scan.browser_id
  WHERE scan.start_time > DATETIME('now', '-30 day')
    AND visit_duration > 60
  ORDER BY visit_duration DESC, visit_start DESC" | column -s '|' -t
