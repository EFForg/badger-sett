#!/usr/bin/env bash

sqlite3 badger.sqlite3 -batch -header "SELECT s.fqdn AS site,
    COUNT(DISTINCT t.base) AS num_trackers
  FROM site s
  JOIN tracking tr ON tr.site_id = s.id
  JOIN tracker t ON t.id = tr.tracker_id
  JOIN scan ON scan.id = tr.scan_id
  WHERE scan.start_time > DATETIME('now', '-30 day')
  GROUP BY s.id
  ORDER BY num_trackers DESC
  LIMIT 30" | column -s '|' -t
