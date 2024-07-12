#!/usr/bin/env bash

# this line from
# https://stackoverflow.com/questions/59895/getting-the-source-directory-of-a-bash-script-from-within
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PB_DIR=$DIR/privacybadger
PB_BRANCH=${PB_BRANCH:-master}
BROWSER=${BROWSER:-chrome}
USER=$(whoami)
LOCKDIR=$DIR/.scan_in_progress

# make sure we're on the latest version of badger-sett
# this function is only called when the script is invoked with GIT_PUSH=1
update_badger_sett_repo() {
  echo "Updating Badger Sett..."

  git fetch

  # figure out whether we need to pull
  LOCAL=$(git rev-parse @)
  REMOTE=$(git rev-parse "@{u}")

  if [ "$LOCAL" != "$REMOTE" ]; then
    echo "Pulling latest version of badger-sett..."
    git pull
  else
    echo "Local badger-sett repository is up-to-date."
  fi
}

# don't run if another instance is still running
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "Another Badger Sett instance is still running!"
  exit 1
fi

trap 'rmdir $LOCKDIR' EXIT

# fetch the latest version of the chosen branch of Privacy Badger
if [ -e "$PB_DIR" ] ; then
  echo "Updating Privacy Badger in $PB_DIR ..."
  cd "$PB_DIR" || exit
  git fetch
  git checkout "$PB_BRANCH"
  # git pull will fail when the remote branch was force pushed to;
  # explicitly discard local revisions/changes and use the latest from remote
  git reset --hard origin/"$PB_BRANCH"
else
  echo "Cloning Privacy Badger into $PB_DIR ..."
  git clone https://github.com/efforg/privacybadger "$PB_DIR"
  cd "$PB_DIR" || exit
  git checkout "$PB_BRANCH"
fi

# change to the badger-sett repository
cd "$DIR" || exit

# If we are planning to push the new results, update the repository now to avoid
# merge conflicts later
if [ "$GIT_PUSH" = "1" ] ; then
  update_badger_sett_repo
fi

printf "Running with "
docker --version

# pull the latest version of the selenium image so we're up-to-date
echo "Pulling latest browser..."
docker pull selenium/standalone-"$BROWSER"

# build the new docker image
echo "Building Docker container..."

# pass in the current user's uid and gid so that the scan can be run with the
# same bits in the container (this prevents permissions issues in the out/ folder)
if ! docker build \
    --build-arg BROWSER="$BROWSER" \
    --build-arg VALIDATE="$GIT_PUSH" \
    --build-arg UID="$(id -u "$USER")" \
    --build-arg GID="$(id -g "$USER")" \
    --build-arg UNAME="$USER" \
    -t badger-sett . ; then
  echo "Docker build failed."
  exit 1;
fi

# create the output folder if necessary
DOCKER_OUT="$(pwd)/docker-out"
mkdir -p "$DOCKER_OUT"

FLAGS=""
echo "Running scan in Docker..."

# If this script is invoked from the command line, use the docker flags "-i -t"
# to allow breaking with Ctrl-C. If it was run by cron, the input device is not
# a TTY, so these flags will cause docker to fail.
if [ "$RUN_BY_CRON" != "1" ] ; then
  echo "Ctrl-C to break."
  FLAGS="-it"
fi

# Run the scan, passing any extra command line arguments to crawler.py
# the --rm tag automatically removes containers & images after the run
# the -v maps the local DOCKER_OUT dir to the /home/USER/out dir in the container
# the --shm-size gives docker access to host's shared memory
if ! docker run --rm $FLAGS \
    -v "$DOCKER_OUT:/home/$USER/out:z" \
    --shm-size="2g" \
    badger-sett "$BROWSER" "$@" ; then
  mv "$DOCKER_OUT"/log.txt ./
  echo "Scan failed. See log.txt for details."
  exit 1;
fi

# update the repo from remote again now to reduce chance of conflict
if [ "$GIT_PUSH" = "1" ] ; then
  update_badger_sett_repo
fi

# copy the updated results and log file out of the docker volume
mv "$DOCKER_OUT"/results.json "$DOCKER_OUT"/log.txt ./

# get the version string from the results file
VERSION=$(python3 -c "import json; print(json.load(open('results.json'))['version'])")
echo "Scan successful. Seed data version: $VERSION"

if [ "$GIT_PUSH" = "1" ] ; then
  # commit updated list
  git add results.json log.txt

  NUM_SITES=$(grep '^  domains to crawl: [0-9]\+$' log.txt | grep -o '[0-9]\+$' | numfmt --to=si)

  # mark custom crawls with an asterisk
  CUSTOM_CRAWL=
  while test $# -gt 0
  do
    case "${1%%=*}" in # %% trims starting from first = char
      --firefox-tracking-protection) CUSTOM_CRAWL="*"; break
        ;;
      --load-extension) CUSTOM_CRAWL="*"; break
        ;;
      *) ;;
    esac
    shift
  done

  git commit -m "Add data $VERSION${CUSTOM_CRAWL} ($PB_BRANCH $BROWSER $NUM_SITES)"
  git push
fi

exit 0
