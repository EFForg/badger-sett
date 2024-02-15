#!/usr/bin/env bash

printf "%-12s%-14s%-18s%-14s%-14s%-14s%-14s\n" \
  BROWSER 'NUM DOMAINS' 'ERRORS (ANTIBOT)' 'TIMEOUT RATE' 'NUM RESTARTS' DURATION 'GIT INFO'

for rev in $(git rev-list HEAD -- log.txt); do
  git --no-pager show "$rev":log.txt > /tmp/log.txt
  num_domains=$(grep 'domains to crawl' /tmp/log.txt | grep -oP '[0-9,]+')
  printf "%-12s%-14s%-18s%-14s%-14s%-14s%-14s\n" \
    "$(grep -oP 'browser: [A-Za-z]+' /tmp/log.txt | cut -d ' ' -f 2- | tr '[:upper:]' '[:lower:]')" \
    "$num_domains" \
    "$(grep 'errored on' /tmp/log.txt | rev | cut -d ' ' -f -2 | rev | cut -d ' ' -f 2- | sed 's/[()]//g') ($(echo "$(grep -c 'security page' /tmp/log.txt) * 100 / $num_domains" | bc -l | xargs printf "%.1f")%)" \
    "$(($(grep -c 'Timed out loading ' /tmp/log.txt) * 100 / num_domains))%" \
    "$(grep -c 'restarted' /tmp/log.txt)" \
    "$((($(grep 'Finished scan' /tmp/log.txt | cut -d " " -f "1,2" | xargs -0 date +%s -d) - $(head -n1 /tmp/log.txt | cut -d " " -f "1,2" | xargs -0 date +%s -d)) / 3600)) hours" \
    "$(git show -s --format="%h  %ci" "$rev")"
done
