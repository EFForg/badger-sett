#!/usr/bin/env bash

# Looks through git history of log.txt to find revisions
# where we saw tracking by the given domain, and prints how
# far down on the site list it was seen and the site domain.
#
# Falls back to searching results.json for old revisions
# where we didn't log new domains in log.txt.
#
# See also: audit.py

if [ -z "$1" ] || [ $# -ne 1 ]; then
  echo "Usage: $0 DOMAIN"
  exit 1
fi

show_trackers_by_site() {
  local query_results
  query_results=$(sqlite3 badger.sqlite3 -batch -header \
    "SELECT site.fqdn AS site, scan.daily_scan, GROUP_CONCAT(DISTINCT tr.base)
      FROM tracking t
      JOIN site ON site.id = t.site_id
      JOIN tracker tr ON tr.id = t.tracker_id
      JOIN scan ON scan.id = t.scan_id
      WHERE scan.start_time > DATETIME('now', '-30 day')
        AND site.fqdn LIKE '%$1%'
      GROUP BY site.fqdn, scan.daily_scan")
  if [ -n "$query_results" ]; then
    echo "Recent trackers on matching site domains:"
    echo "$query_results" | column -s "|" -t
    echo
  fi
}

show_sites_by_tracker() {
  local query_results
  query_results=$(sqlite3 badger.sqlite3 -batch -header \
    "SELECT tr.base AS tracker, scan.daily_scan, GROUP_CONCAT(DISTINCT site.fqdn)
      FROM tracking t
      JOIN site ON site.id = t.site_id
      JOIN tracker tr ON tr.id = t.tracker_id
      JOIN scan ON scan.id = t.scan_id
      WHERE scan.start_time > DATETIME('now', '-30 day')
        AND tr.base LIKE '%$1%'
      GROUP BY tr.base, scan.daily_scan")
  if [ -n "$query_results" ]; then
    echo "Recent site domains with matching trackers:"
    echo "$query_results" | column -s "|" -t
    echo
  fi
}

show_most_recent_matches() {
  local query_results num_results
  query_results=$(sqlite3 badger.sqlite3 -batch -noheader \
    "SELECT tr.base, scan.start_time, b.name, GROUP_CONCAT(site.fqdn), GROUP_CONCAT(DISTINCT tt.name)
      FROM tracking t
      JOIN tracker tr ON t.tracker_id = tr.id
      JOIN scan ON scan.id = t.scan_id
      JOIN browser b ON b.id = scan.browser_id
      JOIN site ON site.id = t.site_id
      LEFT JOIN tracking_type tt ON tt.id = t.tracking_type_id
      WHERE scan.daily_scan = 1
        AND tr.base LIKE '%$1%'
      GROUP BY scan.start_time
      ORDER BY scan.start_time DESC")
  if [ -z "$query_results" ]; then
    printf "No daily scan matches in badger.sqlite3\n\n"
  else
    num_results=$(echo "$query_results" | wc -l)
    echo "Most recent daily scan matches from badger.sqlite3:"
    echo "$query_results" | head -n 10 | column -s "|" -t
    if [ "$num_results" -gt 10 ]; then
      printf "...%s more matches..." $((num_results - 10))
    fi
    printf "\n\n"
  fi
}

if [ -f badger.sqlite3 ]; then
  show_most_recent_matches "$1"
  show_sites_by_tracker "$1"
  show_trackers_by_site "$1"
fi

echo "Searching through git history ..."

tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/search_log.XXXXXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT

for rev in $(git rev-list HEAD -- log.txt); do
  found=
  git --no-pager show "$rev":log.txt > "$tmp_dir/log.txt"
  if grep -Eq '[Nn]ew (domains|trackers) in snitch_map' "$tmp_dir/log.txt"; then
    found=$(grep -m 1 -nE "[Nn]ew (domains|trackers) in snitch_map.*${1//./\\.}" "$tmp_dir/log.txt" | \
      cut -d : -f 1)

    if [ -n "$found" ]; then
      counter=1
      while ! sed -n "$((found-counter))p" "$tmp_dir/log.txt" | grep -Eq '[Vv]isiting [0-9]+:'; do
        counter=$((counter+1))
        [ "$((found-counter))" -eq 0 ] && break
      done

      if [ "$((found-counter))" -eq 0 ]; then
        found=detected-but-unable-to-find-visiting-line
      else
        found=$(sed -n "$((found-counter))p" "$tmp_dir/log.txt" | sed 's/.*isiting \([0-9]\+\): \(.*\)/\1\t\2/')
      fi
    fi

  elif git --no-pager show "$rev":results.json | grep -Eq "^[ ]+\"[^\"]*$1[^\"]*\": \{$"; then
    found=detected-according-to-results-json
  fi

  printf "%s  %-20.20s  %s\n" \
    "$(git show -s --format="%h  %ci" "$rev")" \
    "$(git show -s --format="%s" "$rev" | sed -e 's/^.*(//' -e 's/).*$//' -e 's/\(Add data \|Update seed data: \|master \|from \)//g' | rev | cut -d ' ' -f 1,2 | rev)" \
    "$found"
done
