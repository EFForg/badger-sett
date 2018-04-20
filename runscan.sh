#!/bin/bash

BASEDIR=$HOME/badger-sett/
cd $BASEDIR

# update the repository to avoid merge conflicts later
git pull

# Run main python scanner
source venv/bin/activate
cp results.json results-prev.json
./crawler.py

# Commit updated list to github 
git add results.json results-prev.json
git commit -m "Update seed data: `date`"
git push
