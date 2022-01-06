#!/usr/bin/env bash

# run the scan
if ! ./crawler.py --out-dir "$OUTPATH" --pb-dir "$PBPATH" "$@" ; then
  exit 1
fi

[ "$VALIDATE" != "1" ] && exit 0

# validate the output
if ! ./validate.py "$OUTPATH"/results.json >/dev/null; then
  echo "results.json is invalid"
  exit 1
fi
