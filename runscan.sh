#!/bin/bash

BASEDIR=/home/bennett/badger-sett/
cd $BASEDIR

# Run main python scanner
source venv/bin/activate
cp results.json results-prev.json
./crawler.py

# Commit updated list to github 
git add results.json results-prev.json
git commit -m "Update seed data: `date`"
git push
