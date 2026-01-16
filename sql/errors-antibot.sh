#!/usr/bin/env bash

sqlite3 badger.sqlite3 -batch -header "SELECT STRFTIME('%Y-%m', scan.start_time) AS ym,
    browser.name AS browser,
    SUM(CASE WHEN site_status.name = 'antibot' THEN 1 ELSE 0 END) AS num_antibot,
    SUM(CASE WHEN site_status.name = 'success' THEN 1 ELSE 0 END) AS num_successes,
    ROUND(SUM(CASE WHEN site_status.name = 'antibot' THEN 1 ELSE 0 END) * 1.0 / SUM(CASE WHEN site_status.name = 'success' THEN 1 ELSE 0 END) * 100, 1) || '%' AS antibot_rate
  FROM scan_sites
  JOIN scan ON scan.id = scan_sites.scan_id
  JOIN browser ON browser.id = scan.browser_id
  JOIN site_status ON site_status.id = scan_sites.status_id
  GROUP BY ym, browser.name
  ORDER BY ym DESC, antibot_rate DESC" | column -s '|' -t
