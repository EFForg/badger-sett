#!/usr/bin/env bash

sqlite3 badger.sqlite3 -batch "SELECT s.fqdn AS site,
    COUNT(*) num_records,
    GROUP_CONCAT(DISTINCT t.base) AS fingerprinters
  FROM site s
  JOIN tracking tr ON tr.site_id = s.id
  JOIN tracker t ON t.id = tr.tracker_id
  JOIN tracking_type tt ON tt.id = tr.tracking_type_id
  JOIN scan ON scan.id = tr.scan_id
  WHERE tt.name = 'canvas'
    AND scan.start_time > DATETIME('now', '-30 day')
  GROUP BY s.id
  ORDER BY num_records DESC,
    COUNT(DISTINCT t.base) DESC" | column -s '|' -t
