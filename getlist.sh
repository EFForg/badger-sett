#!/bin/bash

BASEDIR=/home/bennett/badger-sett/
cd $BASEDIR

# pull down latest version of dnt list and copy it to the public-facing web
git pull
echo "copying new Privacy Badger seed data to web endpoint..."
diff /www/eff.org/files/privacybadger-seed.json ./results.json
cp ./results.json /www/eff.org/files/privacybadger-seed.json
