# Badger Sett

> A *sett* or set is a badger's den which usually consists of a network of tunnels
  and numerous entrances. Setts incorporate larger chambers used for sleeping or
  rearing young.

This script is designed to raise young [Privacy Badgers](https://github.com/EFForg/privacybadger) by teaching them
about the trackers on popular sites. Every day, [`crawler.py`](./crawler.py) visits thousands of the top sites from the [Tranco List](https://tranco-list.eu) with the latest version of Privacy Badger, and saves its findings in `results.json`.

See the following EFF.org blog post for more information: [Giving Privacy Badger a Jump Start](https://www.eff.org/deeplinks/2018/08/giving-privacy-badger-jump-start).


## Development setup

1. Install Python 3.8+

2. Create and activate a Python virtual environment:

    ```bash
    python3 -m venv venv
    source ./venv/bin/activate
    pip install -U pip
    ```

    For more, read [this blog post](https://snarky.ca/a-quick-and-dirty-guide-on-how-to-install-packages-for-python/).

3. Install Python dependencies with `pip install -r requirements.txt`

4. Run static analysis with `prospector`

5. Run unit tests with `pytest`

6. Take a look at Badger Sett commandline flags with `./crawler.py --help`

7. Git clone the [Privacy Badger repository](https://github.com/EFForg/privacybadger) somewhere

8. Try running a tiny scan:

    ```bash
    ./crawler.py firefox 5 --no-xvfb --log-stdout --pb-dir /path/to/privacybadger
    ```


## Production setup with Docker

Docker takes care of all dependencies, including setting up the latest browser version.

However, Docker brings its own complexity. Problems from improper file ownership and permissions are a particular pain point.

0. Prerequisites: have [Docker](https://docs.docker.com/get-docker/) installed.
   Make sure your user is part of the `docker` group so that you can build and
   run docker images without `sudo`. You can add yourself to the group with

   ```
   $ sudo usermod -aG docker $USER
   ```

1. Clone the repository

   ```
   $ git clone https://github.com/efforg/badger-sett
   ```

2. Run a scan

   ```
   $ BROWSER=firefox ./runscan.sh 500
   ```

   This will scan the top 500 sites on the Tranco list in Chrome
   with the latest version of Privacy Badger's master branch.

   To run the script with a different branch of Privacy Badger, set the `PB_BRANCH`
   variable. e.g.

   ```
   $ PB_BRANCH=my-feature-branch BROWSER=firefox ./runscan.sh 500
   ```

   You can also pass arguments to `crawler.py`, the Python script that does
   the actual crawl. Any arguments passed to `runscan.sh` will be
   forwarded to `crawler.py`. For example, to exclude all websites ending
   with .gov and .mil from your website visit list:

   ```
   $ BROWSER=edge ./runscan.sh 500 --exclude .gov,.mil
   ```

3. Monitor the scan

   To have the scan print verbose output about which sites it's visiting, use
   the `--log-stdout` argument.

   If you don't use that argument, all output will still be logged to
   `docker-out/log.txt`, beginning after the script outputs "Running scan in
   Docker..."

### Automatic scanning

To set up the script to run periodically and automatically update the
repository with its results:

1. Create a new ssh key with `ssh-keygen`. Give it a name unique to the
   repository.

   ```
   $ ssh-keygen
   Generating public/private rsa key pair.
   Enter file in which to save the key (/home/USER/.ssh/id_rsa): /home/USER/.ssh/id_rsa_badger_sett
   ```

2. Add the new key as a deploy key with R/W access to the repo on Github.
   https://developer.github.com/v3/guides/managing-deploy-keys/

3. Add a SSH host alias for Github that uses the new key pair. Create or open
   `~/.ssh/config` and add the following:

   ```
   Host github-badger-sett
     HostName github.com
     User git
     IdentityFile /home/USER/.ssh/id_rsa_badger_sett
   ```

4. Configure git to connect to the remote over SSH. Edit `.git/config`:

   ```
   [remote "origin"]
     url = ssh://git@github-badger-sett:/efforg/badger-sett
   ```

   This will have `git` connect to the remote using the new SSH keys by default.

5. Create a cron job to call `runscan.sh` once a day. Set the environment
   variable `RUN_BY_CRON=1` to turn off TTY forwarding to `docker run` (which
   would break the script in cron), and set `GIT_PUSH=1` to have the script
   automatically commit and push `results.json` when the scan finishes. Here's an
   example `crontab` entry:

   ```
   0 0 * * *  RUN_BY_CRON=1 GIT_PUSH=1 BROWSER=chrome /home/USER/badger-sett/runscan.sh 6000 --exclude=.mil,.gov
   ```

6. If everything has been set up correctly, the script should push a new version
   of `results.json` after each scan.
