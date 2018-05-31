#!/bin/bash

# run the crawler from the directory with the extension in it
cd /home/$USER
./crawler.py --out-path $OUTPATH --ext-path /home/$USER/privacy-badger.xpi
