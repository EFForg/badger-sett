#!/usr/bin/env bash

cd "$(dirname "$0")" || exit;

lockdir=../.scan_in_progress
logfile=../docker-out/log.txt

# if a scan is in progress
if [ ! -d "$lockdir" ]; then
  exit
fi

# and the log file exists
if [ ! -f "$logfile" ]; then
  exit
fi

# and if the log file hasn't been updated in a while
if [ ! "$(find "$logfile" -newermt "6 minutes ago")" ]; then

  # TODO it's possible we are still in the middle of restarting here

  browser=$(grep -oP 'browser: [A-Za-z]+' "$logfile" | cut -d ' ' -f 2-)

  # force a restart by killing the browser
  if [ "$browser" = Chrome ]; then
    pkill chrome
  elif [ "$browser" = Firefox ]; then
    pkill firefox-bin
  elif [ "$browser" = Edge ]; then
    pkill microsoft-edge
  fi
fi
