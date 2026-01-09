#!/usr/bin/env bash

sqlite3 badger.sqlite3 -batch -header "SELECT
    start_site.fqdn AS 'initial site',
    (CASE WHEN start_site.id = end_site.id THEN '-' ELSE end_site.fqdn END) AS 'final site',
    COUNT(*) AS count
  FROM scan_sites
  JOIN site AS start_site ON start_site.id = initial_site_id
  JOIN site AS end_site ON end_site.id = final_site_id
  JOIN scan ON scan.id = scan_id
  WHERE scan.start_time > DATETIME('now', '-30 day')
    AND scan.no_blocking = 1
    AND status_id = 1
    AND final_site_id NOT IN (
      SELECT DISTINCT tr.site_id
      FROM tracking AS tr
      JOIN scan ON scan.id = tr.scan_id
      WHERE scan.start_time > DATETIME('now', '-30 day')
        AND scan.no_blocking = 1)
  GROUP BY start_site.fqdn, end_site.fqdn
  ORDER BY count DESC, end_site.fqdn ASC, start_site.fqdn ASC" | column -s '|' -t
