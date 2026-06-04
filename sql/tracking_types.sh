#!/usr/bin/env bash

general_overview() {
  local from="$1"
  local to="$2"
  local tracking_type="$3"

  printf "** %s trackers seen on 3+ sites (%s, %s) **\n\n" \
    "$tracking_type" "$from" "$to"

  sqlite3 badger.sqlite3 -batch -header "SELECT t.base,
    COUNT(DISTINCT s.fqdn) num_sites,
    COUNT(DISTINCT scan.id) num_scans
    FROM tracker t
    JOIN tracking tr ON tr.tracker_id = t.id
    JOIN site s ON s.id = tr.site_id
    JOIN tracking_type tt ON tt.id = tr.tracking_type_id
    JOIN scan ON scan.id = tr.scan_id
    WHERE tt.name = '$tracking_type'
      AND scan.start_time > DATETIME('now', '-$from')
      AND scan.start_time <= DATETIME('now', '-$to')
      AND scan.daily_scan = 1
    GROUP BY t.id
    HAVING COUNT(DISTINCT s.fqdn) > 2
    ORDER BY num_sites DESC, num_scans DESC" | column -s '|' -t

  echo
}

one_browser_only() {
  local browser="$1"
  local tracking_type="$2"

  printf "** %s-exclusive %s trackers (60d) **\n\n" "$browser" "$tracking_type"

  sqlite3 badger.sqlite3 -batch -header "SELECT t.base,
    COUNT(DISTINCT s.fqdn) num_sites,
    COUNT(DISTINCT scan.id) num_scans
    FROM tracker t
    JOIN tracking tr ON tr.tracker_id = t.id
    JOIN site s ON s.id = tr.site_id
    JOIN tracking_type tt ON tt.id = tr.tracking_type_id
    JOIN scan ON scan.id = tr.scan_id
    JOIN browser ON browser.id = scan.browser_id
    WHERE browser.name = '$browser'
      AND tt.name = '$tracking_type'
      AND scan.start_time > DATETIME('now', '-60 day')
      AND scan.daily_scan = 1
      AND t.id NOT IN (SELECT t2.id
        FROM tracker t2
        JOIN tracking tr2 ON tr2.tracker_id = t2.id
        JOIN tracking_type tt2 ON tt2.id = tr2.tracking_type_id
        JOIN scan s2 ON s2.id = tr2.scan_id
        JOIN browser b2 ON b2.id = s2.browser_id
        WHERE b2.name != '$1'
          AND tt2.name = '$tracking_type'
          AND s2.start_time > DATETIME('now', '-60 day')
          AND s2.daily_scan = 1)
    GROUP BY t.id, browser.name
    ORDER BY num_sites DESC, num_scans DESC" | column -s '|' -t

  echo
}

newly_detected() {
  local tracking_type="$1"

  printf "** new 3+ site %s trackers (30d, 6m) **\n\n" "$tracking_type"

  sqlite3 badger.sqlite3 -batch -header "SELECT t.base,
    COUNT(DISTINCT s.fqdn) num_sites,
    COUNT(DISTINCT scan.id) num_scans
    FROM tracker t
    JOIN tracking tr ON tr.tracker_id = t.id
    JOIN site s ON s.id = tr.site_id
    JOIN tracking_type tt ON tt.id = tr.tracking_type_id
    JOIN scan ON scan.id = tr.scan_id
    WHERE tt.name = '$tracking_type'
      AND scan.start_time > DATETIME('now', '-30 day')
      AND scan.daily_scan = 1
      AND t.id NOT IN (SELECT t2.id
          FROM tracker t2
          JOIN tracking tr2 ON tr2.tracker_id = t2.id
          JOIN site site2 ON site2.id = tr2.site_id
          JOIN tracking_type tt2 ON tt2.id = tr2.tracking_type_id
          JOIN scan s2 ON s2.id = tr2.scan_id
          JOIN browser b2 ON b2.id = s2.browser_id
          WHERE tt2.name = '$tracking_type'
            AND s2.start_time > DATETIME('now', '-6 month')
            AND s2.start_time <= DATETIME('now', '-30 day')
            AND s2.daily_scan = 1
          GROUP BY t2.id 
          HAVING COUNT(DISTINCT site2.fqdn) > 2)
    GROUP BY t.id
    HAVING COUNT(DISTINCT s.fqdn) > 2
    ORDER BY num_sites DESC, num_scans DESC" | column -s '|' -t

  echo
}

no_longer_detected() {
  local curr=$1
  local prev=$2
  local tracking_type=$3

  printf "** no longer detected 3+ site %s trackers (%s, %s) **\n\n" \
    "$tracking_type" "$curr" "$prev"

  sqlite3 badger.sqlite3 -batch -header "SELECT t.base,
    COUNT(DISTINCT site.fqdn) num_sites,
    COUNT(DISTINCT scan.id) num_scans,
    MAX(scan_sites.end_time) 'last seen on'
    FROM tracker t
    JOIN tracking tr ON tr.tracker_id = t.id
    JOIN site ON site.id = tr.site_id
    JOIN tracking_type tt ON tt.id = tr.tracking_type_id
    JOIN scan ON scan.id = tr.scan_id
    JOIN scan_sites ON scan_sites.scan_id = tr.scan_id
      AND scan_sites.initial_site_id = tr.site_id
    WHERE tt.name = '$tracking_type'
      AND scan.start_time > DATETIME('now', '-$prev')
      AND scan.start_time <= DATETIME('now', '-$curr')
      AND scan.daily_scan = 1
      AND t.id NOT IN (SELECT t2.id
          FROM tracker t2
          JOIN tracking tr2 ON tr2.tracker_id = t2.id
          JOIN site site2 ON site2.id = tr2.site_id
          JOIN tracking_type tt2 ON tt2.id = tr2.tracking_type_id
          JOIN scan s2 ON s2.id = tr2.scan_id
          WHERE tt2.name = '$tracking_type'
            AND s2.start_time > DATETIME('now', '-$curr')
            AND s2.daily_scan = 1
          GROUP BY t2.id 
          HAVING COUNT(DISTINCT site2.fqdn) > 2)
    GROUP BY t.id
    HAVING COUNT(DISTINCT site.fqdn) > 2
    ORDER BY num_sites DESC, num_scans DESC" | column -s '|' -t

  echo
}

invalid_hosts() {
  printf "** most recent invalid tracker hostnames **\n\n"

  sqlite3 badger.sqlite3 -batch -header "SELECT scan.start_time scan_date,
    tracker.base tracker_base,
    site.fqdn site_fqdn,
    browser.name browser,
    tt.name 'tracking types'
    FROM tracking
    JOIN tracking_type tt ON tt.id = tracking.tracking_type_id
    JOIN tracker ON tracker.id = tracking.tracker_id
    JOIN scan ON scan.id = tracking.scan_id
    JOIN browser ON browser.id = scan.browser_id
    JOIN site ON site.id = tracking.site_id
    WHERE tracker.base NOT LIKE '%.%'
    ORDER BY scan.start_time DESC LIMIT 30" | column -s '|' -t

  echo
}

general_overview "120 day" "60 day" canvas
general_overview "60 day" "0 day" canvas

one_browser_only firefox canvas
one_browser_only chrome canvas
one_browser_only firefox beacon
one_browser_only chrome beacon

newly_detected canvas
newly_detected beacon
newly_detected pixelcookieshare

no_longer_detected "1 month" "6 month" canvas
no_longer_detected "7 day" "1 month" canvas

invalid_hosts
