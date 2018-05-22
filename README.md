# Badger Sett

> A *sett* or set is a badger's den which usually consists of a network of tunnels
  and numerous entrances. Setts incorporate larger chambers used for sleeping or
  rearing young.

This script is designed to raise young Privacy Badgers by teaching them a little
about the trackers on popular sites, thus preparing them to fight trackers out
in the wild. `crawler.py` visits the top 10,000 sites of the Majestic Million
with a fresh version of Privacy Badger installed and saves the `action_map` and
`snitch_map` it learns in `results.json`. 

To set up:

1. Clone this repository into the home directory of the user which will run the
   crawler

```
$ cd ~
$ git clone https://github.com/efforg/badger-sett
```

2. Build the docker image

```
$ sudo docker build -t badger-sett .
```

3. Create a new ssh key with `ssh-keygen`, add it as a deploy key with R/W
   access to the github repository, and configure git to connect to the remote
   over SSH.

4. Set up a cron job to call `runscan.sh` periodically, e.g. once a week.
   `runscan.sh` is written assuming the repository has been cloned into the
   calling user's home directory and that the script hasn't been moved or copied
   anywhere else.

5. If everything has been set up correctly, the script should push a new version
   of `results.json` after each crawl. Whenever you `make` a new version of
   Privacy Badger, it should pull the latest version of the crawler's data and
   ship it with the new version of the extension.
