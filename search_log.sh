#!/usr/bin/env bash

# Looks through git history of log.txt to find revisions
# where we saw tracking by the given domain, and prints
# the matching line number.
#
# See also: audit.py

if [ -z "$1" ] || [ $# -ne 1 ]; then
  echo "Usage: $0 DOMAIN"
  exit 1
fi

for rev in $(git rev-list HEAD -- log.txt); do
  echo "$(git show -s --format="%h  %ci" "$rev")  $(git --no-pager show "$rev":log.txt | grep -nE "New domains.*$1" | cut -d : -f 1)"
done
