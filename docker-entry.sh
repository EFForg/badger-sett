#!/bin/bash

# run the scan
if ! ./crawler.py --out-path $OUTPATH --pb-path $PBPATH "$@" ; then
  exit 1
fi

if [ "$VALIDATE" != "1" ] ; then exit 0; fi

# validate the output and print a summary of the changes
if ! ./validate.py old-results.json $OUTPATH/results.json ; then 
  echo "results.json is invalid."
  exit 1
fi
