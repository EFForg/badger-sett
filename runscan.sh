#!/bin/bash

# this line from
# https://stackoverflow.com/questions/59895/getting-the-source-directory-of-a-bash-script-from-within
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PB_DIR=$DIR/privacybadger
PB_BRANCH=${PB_BRANCH:-master}
BROWSER=${BROWSER:-chrome}
USER=$(whoami)

# fetch the latest version of the chosen branch of Privacy Badger
if [ -e "$PB_DIR" ] ; then
  echo "Updating Privacy Badger..."
  cd "$PB_DIR"
  git fetch
  git checkout "$PB_BRANCH"
  git pull
else
  echo "Cloning Privacy Badger..."
  git clone https://github.com/efforg/privacybadger "$PB_DIR"
  cd "$PB_DIR"
  git checkout "$PB_BRANCH"
fi

# change to the badger-sett repository
cd "$DIR"

# If we are planning to push the new results, update the repository now to avoid
# merge conflicts later
if [ "$GIT_PUSH" = "1" ] ; then
  echo "Updating Badger Sett..."

  git fetch

  # figure out whether we need to pull
  UPSTREAM=${1:-'@{u}'}
  LOCAL=$(git rev-parse @)
  REMOTE=$(git rev-parse "$UPSTREAM")

  if [ "$LOCAL" != "$REMOTE" ]; then
    echo "Pulling latest version of badger-sett..."
    git pull
  else
    echo "Local badger-sett repository is up-to-date."
  fi
fi

# build the new docker image
echo "Building Docker container..."

# pass in the current user's uid and gid so that the scan can be run with the
# same bits in the container (this prevents permissions issues in the out/ folder)
if ! docker build --build-arg BROWSER="$BROWSER" \
    --build-arg VALIDATE="$GIT_PUSH" \
    --build-arg UID="$(id -u "$USER")" \
    --build-arg GID="$(id -g "$USER")" \
    --build-arg UNAME="$USER" -t badger-sett . ; then
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
# Run in Firefox:
if ! docker run $FLAGS \
    -v "$DOCKER_OUT:/home/$USER/out:z" \
    -v /dev/shm:/dev/shm \
    badger-sett --browser "$BROWSER" "$@" ; then
  mv "$DOCKER_OUT"/log.txt ./
  echo "Scan failed. See log.txt for details."
  exit 1;
fi

# Run in Chrome (seccomp doesn't work in jessie):
#docker run -t -i \
  #-v $DOCKER_OUT:/home/$USER/out:z \
  #-v /dev/shm:/dev/shm \
  #--device /dev/dri \
  #--security-opt seccomp=./chrome-seccomp.json \
  #badger-sett "$@"

# back up old results
cp results.json results-prev.json

# copy the updated results and log file out of the docker volume
mv "$DOCKER_OUT"/results.json "$DOCKER_OUT"/log.txt ./

# Get the version string from the results file
VERSION=$(python3 -c "import json; print(json.load(open('results.json'))['version'])")
echo "Scan successful. Seed data version: $VERSION"

if [ "$GIT_PUSH" = "1" ] ; then
  echo "Updating public repository."

  # Commit updated list to github
  git add results.json log.txt
  git commit -m "Update seed data: $VERSION"
  git push
fi

exit 0
