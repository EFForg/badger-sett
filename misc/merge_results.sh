#!/usr/bin/env bash

# Given a start (and an optional end) revision,
# prints the command to produce the combined results.json
# for all versions of results.json in the range.
#
# This is a wrapper around crawler.py's --num-sites 0 --load-data <(git show aaaaaa:results.json) --load-data <(bbbbbb:results.json) ...

if [ -z "$1" ] || [ $# -gt 2 ] || [ $# -lt 1 ]; then
  echo "Usage: $0 GIT_START_REV [GIT_END_REV]"
  exit 1
fi

merge_results() {
  local first=$1
  local last=$2

  shift
  shift

  local revisions
  revisions=$(git rev-list "$first"^.."$last" -- results.json)
  [ -z "$revisions" ] && exit 1
  for rev in $revisions; do
    set -- "--load-data=<(git show ${rev}:results.json)" "$@"
  done

  printf "./crawler.py chrome 0 --pb-dir ../privacybadger/ %s\\n" \\
  for arg in "${@:1:${#@}-1}"; do
    printf "  %s %s\n" "$arg" \\
  done
  printf "  %s\n" "${@:$#}" # and now print the last element
}

merge_results "$1" "$2"
