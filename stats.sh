#!/usr/bin/env bash

tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/badger_sett_stats.XXXXXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT

printf "%-11s%-8s%-10s%-24s%-9s%-12s%-14s\n" \
  BROWSER SITES TRACKERS 'ERRORS (TMOs, ANTIBOT)' CRASHES DURATION 'GIT INFO'

for rev in $(git rev-list HEAD -- log.txt); do
  log_txt="$tmp_dir/log.txt"
  git --no-pager show "$rev":log.txt > "$log_txt"
  num_domains=$(grep 'domains to crawl' "$log_txt" | grep -oE '[0-9,]+')

  printf "%-11s%-8s%-10s%6s%-18s%-9s%-12s%-14s\n" \
    "$(grep -oE 'browser: [A-Za-z]+' "$log_txt" | cut -d ' ' -f 2- | tr '[:upper:]' '[:lower:]')" \
    "$num_domains" \
    "$(./validate.py <(git --no-pager show "$rev:results.json") 2>/dev/null | grep 'Newly blocked domains' | grep -oE '[0-9]+')" \
    "$(grep 'errored on' "$log_txt" | rev | cut -d ' ' -f -2 | rev | cut -d ' ' -f 2- | sed 's/[()]//g')" \
    " ($(echo "$(grep -c 'Timed out loading ' "$log_txt") * 100 / $num_domains" | bc -l | xargs printf "%.1f")%, $(echo "$(grep -c 'security page' "$log_txt") * 100 / $num_domains" | bc -l | xargs printf "%.1f")%)" \
    "$(grep -c 'restarted' "$log_txt")" \
    "$((($(grep 'Finished scan' "$log_txt" | cut -d " " -f "1,2" | xargs -0 date +%s -d) - $(head -n1 "$log_txt" | cut -d " " -f "1,2" | xargs -0 date +%s -d)) / 3600)) hours" \
    "$(git show -s --format="%h  %ci" "$rev")"
done
