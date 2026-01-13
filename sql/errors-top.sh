#!/usr/bin/env bash

sqlite3 badger.sqlite3 -batch -header "SELECT STRFTIME('%Y', scan.start_time) AS year,
    browser.name AS browser,
    error.name AS 'error name',
    COUNT(*) AS num
  FROM error
  JOIN scan_sites ON error_id = error.id
  JOIN scan ON scan.id = scan_sites.scan_id
  JOIN browser ON browser.id = scan.browser_id
  GROUP BY year, browser.name, error.name
  ORDER BY year DESC, num DESC" | column -s '|' -t
