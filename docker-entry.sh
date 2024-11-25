#!/usr/bin/env bash

# run the scan
if ! ./crawler.py --out-dir "$OUTPATH" --pb-dir "$PBPATH" "$@" ; then
  exit 1
fi

exit 0
