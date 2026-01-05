#!/usr/bin/env bash

print_stats() {
  browser="$1"

  no_blocking=0
  blocking_mode_text=
  if [ -n "$2" ]; then
    blocking_mode_text="no-blocking "
    no_blocking=1
  fi

  region_col=
  daily_scan=1
  if [ -n "$3" ]; then
    region_col=region,
    daily_scan=0
    blocking_mode_text="distributed scan "
  fi

  num_days=60
  if [ -n "$4" ]; then
    num_days="$4"
  fi

  printf "** %s %s**\n\n" "$browser" "$blocking_mode_text"

  sqlite3 badger.sqlite3 -batch -header -column "SELECT start_time, end_time,
      ROUND((CAST(STRFTIME('%s', end_time) AS FLOAT) -
          CAST(STRFTIME('%s', start_time) AS FLOAT)) / 60 / 60, 1) AS num_hours,
      $region_col
      num_sites,
      COUNT(DISTINCT blocked_trackers.tracker_id) AS num_blocked,
      ROUND(scan_sites.num_errors * 1.0 / num_sites * 100, 1) || '%' AS error_rate
    FROM scan
    JOIN browser ON browser.id = scan.browser_id
    JOIN (SELECT scan.id AS scan_id,
        tr.tracker_id
      FROM scan
      JOIN browser ON browser.id = scan.browser_id
      JOIN tracking tr ON tr.scan_id = scan.id
      WHERE scan.start_time > DATETIME('now', '-$num_days day')
      GROUP BY tr.scan_id, tr.tracker_id
      HAVING COUNT(DISTINCT tr.site_id) > 2)
        AS blocked_trackers ON blocked_trackers.scan_id = scan.id
    JOIN (SELECT scan_id, COUNT(*) AS num_errors
      FROM scan_sites
      JOIN scan ON scan.id = scan_id
      WHERE status_id != 1
        AND scan.start_time > DATETIME('now', '-$num_days day')
      GROUP BY scan_id)
        AS scan_sites ON scan_sites.scan_id = scan.id
    WHERE start_time > DATETIME('now', '-$num_days day')
      AND browser.name = '$browser'
      AND no_blocking = '$no_blocking'
      AND daily_scan = '$daily_scan'
    GROUP BY scan.id
    ORDER BY scan.start_time DESC"

  echo
}

print_distributed_scan_stats() {
  browser="$1"
  print_stats "$browser" 1 1 365
}

echo

print_stats "chrome"
print_stats "chrome" 1

print_stats "firefox"
print_stats "firefox" 1

print_stats "edge"

print_distributed_scan_stats "chrome"
print_distributed_scan_stats "firefox"
