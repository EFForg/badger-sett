#!/usr/bin/env bash

sqlite3 badger.sqlite3 -batch -header "SELECT STRFTIME('%Y-%m', scan.start_time) AS ym,
    browser.name AS browser,
    COUNT(*) AS num
  FROM error
  JOIN scan_sites ON error_id = error.id
  JOIN scan ON scan.id = scan_sites.scan_id
  JOIN browser ON browser.id = scan.browser_id
  JOIN site_status ON site_status.id = scan_sites.status_id
  WHERE site_status.name = 'antibot'
  GROUP BY ym, browser.name
  ORDER BY ym DESC, num DESC" | column -s '|' -t
