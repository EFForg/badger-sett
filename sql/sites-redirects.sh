#!/usr/bin/env bash

sqlite3 badger.sqlite3 -batch -header "SELECT
  start_site.fqdn AS initial_site_fqdn,
  end_site.fqdn AS final_site_fqdn,
  COUNT(*) AS count
  FROM scan_sites
  JOIN site AS start_site ON start_site.id = initial_site_id
  JOIN site AS end_site ON end_site.id = final_site_id
  JOIN scan ON scan.id = scan_id
  WHERE scan.start_time > DATETIME('now', '-30 day')
    AND initial_site_id != final_site_id
  GROUP BY initial_site_id, final_site_id
  ORDER BY count DESC, initial_site_fqdn ASC" | column -s '|' -t
