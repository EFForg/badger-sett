# Badger Sett

> A *sett* or set is a badger's den which usually consists of a network of tunnels
  and numerous entrances. Setts incorporate larger chambers used for sleeping or
  rearing young.

This script is designed to raise young Privacy Badgers by teaching them a little
about the trackers on popular sites, thus preparing them to fight trackers out
in the wild. `crawler.py` visits the top 2,000 sites of the Majestic Million
with a fresh version of Privacy Badger installed and saves the `action_map` and
`snitch_map` it learns in `results.json`.

## Setup

0. Prerequisites: [Docker](https://docs.docker.com/install/)

1. Clone the repository

```
$ git clone https://github.com/efforg/badger-sett
```

2. Run a scan 

```
$ ./runscan.sh
```

This will run a scan with the latest version of Privacy Badger's master branch and won't commit the results.

To run the script with a different branch, set the `PB_BRANCH` variable. e.g.

```
$ PB_BRANCH=my-feature-branch ./runscan.sh
```

### Automatic crawling

To set up the script to run periodically and automatically update the
repository with its results:

1. Create a new ssh key with `ssh-keygen`, add it as a deploy key with R/W
   access to the github repository, and configure git to connect to the remote
   over SSH.

2. Set a cron job to call `runscan.sh` once a day. Set the env var `GIT_PUSH=1`
   to have the script automatically commit and push `results.json` when a scan
   finishes. Here's an example `crontab` entry:

```
0 0 * * *  GIT_PUSH=1 /home/user/badger-sett/runscan.sh
```

Make sure the script has permissions to run `docker` as a superuser.

3. If everything has been set up correctly, the script should push a new version
   of `results.json` after each crawl. Soon, whenever you `make` a new version of
   Privacy Badger, it should pull the latest version of the crawler's data and
   ship it with the new version of the extension.
