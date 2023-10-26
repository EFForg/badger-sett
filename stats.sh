#!/usr/bin/env bash

printf "%-14s%-14s%-14s%-14s%-14s%-14s%-14s\n" \
  BROWSER 'NUM DOMAINS' 'ERROR RATE' 'TIMEOUT RATE' 'NUM RESTARTS' ANTIBOT 'GIT INFO'

for rev in $(git rev-list HEAD -- log.txt); do
  git --no-pager show "$rev":log.txt > /tmp/log.txt
  num_domains=$(grep 'domains to crawl' /tmp/log.txt | grep -oP '[0-9,]+')
  printf "%-14s%-14s%-14s%-14s%-14s%-14s%-14s\n" \
    "$(grep -oP ''"'"'browserName'"'"': '"'"'[A-Za-z]+'"'"'' /tmp/log.txt | cut -d ' ' -f 2- | sed 's/['"'"']//g')" \
    "$num_domains" \
    "$(grep 'errored on' /tmp/log.txt | rev | cut -d ' ' -f -2 | rev | cut -d ' ' -f 2- | sed 's/[()]//g')" \
    "$(($(grep -c 'Timed out loading ' /tmp/log.txt) * 100 / num_domains))%" \
    "$(grep -c 'restarted' /tmp/log.txt)" \
    "$(($(grep -c 'security page' /tmp/log.txt) * 100 / num_domains))%" \
    "$(git show -s --format="%h  %ci" "$rev")"
done
