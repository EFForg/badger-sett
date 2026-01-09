#!/usr/bin/env bash

sqlite3 badger.sqlite3 -batch -header "SELECT STRFTIME('%Y', scan.start_time) AS year,
  browser.name AS browser,
  error.name AS 'crash name',
  COUNT(*) AS num
  FROM scan_crashes
  JOIN error ON error.id = scan_crashes.error_id
  JOIN scan ON scan.id = scan_crashes.scan_id
  JOIN browser ON browser.id = scan.browser_id
  GROUP BY year, browser.id, error.id
  ORDER BY year DESC, num DESC" | column -s '|' -t
