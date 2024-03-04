#!/usr/bin/env bash

printf "%-11s%-8s%-10s%-24s%-9s%-12s%-14s\n" \
  BROWSER SITES TRACKERS 'ERRORS (TMOs, ANTIBOT)' CRASHES DURATION 'GIT INFO'

for rev in $(git rev-list HEAD -- log.txt); do
  git --no-pager show "$rev":log.txt > /tmp/log.txt
  num_domains=$(grep 'domains to crawl' /tmp/log.txt | grep -oP '[0-9,]+')
  printf "%-11s%-8s%-10s%6s%-18s%-9s%-12s%-14s\n" \
    "$(grep -oP 'browser: [A-Za-z]+' /tmp/log.txt | cut -d ' ' -f 2- | tr '[:upper:]' '[:lower:]')" \
    "$num_domains" \
    "$(./validate.py <(git --no-pager show "$rev:results.json") 2>/dev/null | grep 'Newly blocked domains' | grep -oP '[\d]+')" \
    "$(grep 'errored on' /tmp/log.txt | rev | cut -d ' ' -f -2 | rev | cut -d ' ' -f 2- | sed 's/[()]//g')" \
    " ($(echo "$(grep -c 'Timed out loading ' /tmp/log.txt) * 100 / $num_domains" | bc -l | xargs printf "%.1f")%, $(echo "$(grep -c 'security page' /tmp/log.txt) * 100 / $num_domains" | bc -l | xargs printf "%.1f")%)" \
    "$(grep -c 'restarted' /tmp/log.txt)" \
    "$((($(grep 'Finished scan' /tmp/log.txt | cut -d " " -f "1,2" | xargs -0 date +%s -d) - $(head -n1 /tmp/log.txt | cut -d " " -f "1,2" | xargs -0 date +%s -d)) / 3600)) hours" \
    "$(git show -s --format="%h  %ci" "$rev")"
done
