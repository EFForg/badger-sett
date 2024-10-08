#!/usr/bin/env bash

sqlite3 badger.sqlite3 -batch -header "SELECT t.base,
  COUNT(DISTINCT s.fqdn) num_sites
  FROM tracker t
  JOIN tracking tr ON tr.tracker_id = t.id
  JOIN site s ON s.id = tr.site_id
  JOIN tracking_type tt ON tt.id = tr.tracking_type_id
  JOIN scan ON scan.id = tr.scan_id
  WHERE tt.name = 'beacon'
    AND scan.start_time > DATETIME('now', '-30 day')
    AND t.id NOT IN (SELECT t2.id
      FROM tracker t2
      JOIN tracking tr2 ON tr2.tracker_id = t2.id
      JOIN scan scan2 ON scan2.id = tr2.scan_id
      LEFT JOIN tracking_type tt2 ON tt2.id = tr2.tracking_type_id
      WHERE scan2.start_time > DATETIME('now', '-30 day')
        AND (tt2.name != 'beacon'
          OR tr2.tracking_type_id IS NULL)
      GROUP BY t2.id
      HAVING COUNT(tr2.site_id) > 2)
  GROUP BY t.id
  ORDER BY num_sites DESC
  LIMIT 30" | column -s '|' -t
