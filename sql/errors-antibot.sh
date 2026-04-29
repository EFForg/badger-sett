#!/usr/bin/env bash

sqlite3 badger.sqlite3 -batch -header "SELECT *,
  ROUND(num_antibot * 1.0 / (num_successes + num_antibot) * 100, 1) || '%' AS antibot_rate
    FROM (SELECT STRFTIME('%Y-%m', scan.start_time) AS ym,
      SUM(CASE WHEN site_status.name = 'antibot' THEN 1 ELSE 0 END) AS num_antibot,
      SUM(CASE WHEN site_status.name = 'success' THEN 1 ELSE 0 END) AS num_successes
    FROM scan_sites
    JOIN scan ON scan.id = scan_sites.scan_id
    JOIN site_status ON site_status.id = scan_sites.status_id
    WHERE scan.daily_scan = 1
    GROUP BY ym) AS x
  ORDER BY ym DESC, antibot_rate DESC, num_successes DESC" | column -s '|' -t
