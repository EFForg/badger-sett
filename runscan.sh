#!/bin/bash

cd $BADGER_BASEDIR

# update the repository to avoid merge conflicts later
git pull

# Run main python scanner
cp results.json results-prev.json
./crawler.py

# Commit updated list to github 
git add results.json results-prev.json
git commit -m "Update seed data: `date`"
git push
