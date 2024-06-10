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

tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/search_log.XXXXXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT

for rev in $(git rev-list HEAD -- log.txt); do
  found=
  git --no-pager show "$rev":log.txt > "$tmp_dir/log.txt"
  if grep -Eq '[Nn]ew (domains|trackers) in snitch_map' "$tmp_dir/log.txt"; then
    found=$(grep -m 1 -nE "[Nn]ew (domains|trackers) in snitch_map.*$1" "$tmp_dir/log.txt" | \
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
