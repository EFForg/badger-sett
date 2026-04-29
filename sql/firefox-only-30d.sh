#!/usr/bin/env bash

sqlite3 badger.sqlite3 -batch -header "SELECT t.base,
    COALESCE(GROUP_CONCAT(DISTINCT tt.name), '-') AS 'tracking types',
    COUNT(DISTINCT site.id) num_sites,
    COUNT(DISTINCT s.id) num_scans
  FROM tracker t
  JOIN tracking tr ON tr.tracker_id = t.id
  JOIN scan s ON s.id = tr.scan_id
  JOIN site ON site.id = tr.site_id
  LEFT JOIN tracking_type tt ON tt.id = tr.tracking_type_id
  WHERE s.browser_id = 1
    AND s.daily_scan = 1
    AND s.start_time > DATETIME('now', '-30 day')
    AND t.id NOT IN (SELECT t2.id
      FROM tracker t2
      JOIN tracking tr2 ON tr2.tracker_id = t2.id
      JOIN scan s2 ON s2.id = tr2.scan_id
      WHERE s2.browser_id != 1
        AND s2.daily_scan = 1
        AND s2.start_time > DATETIME('now', '-30 day'))
  GROUP BY t.id
  ORDER BY num_sites DESC, num_scans DESC
  LIMIT 30" | column -s '|' -t
