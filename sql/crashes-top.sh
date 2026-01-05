#!/usr/bin/env bash

sqlite3 badger.sqlite3 -batch -header "SELECT STRFTIME('%Y', scan.start_time) AS year,
  crash.name AS 'crash name',
  COUNT(*) AS num
  FROM scan_crashes
  JOIN crash ON crash.id = scan_crashes.crash_id
  JOIN scan ON scan.id = scan_crashes.scan_id
  GROUP BY crash.id, year
  ORDER BY year DESC, num DESC" | column -s '|' -t
