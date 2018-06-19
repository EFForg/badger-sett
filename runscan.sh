#!/bin/bash

# this line from
# https://stackoverflow.com/questions/59895/getting-the-source-directory-of-a-bash-script-from-within
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PB_DIR=$DIR/privacybadger
PB_BRANCH=${PB_BRANCH:-master}
USER=$(whoami)

# fetch and build the latest version of Privacy Badger
if [ -e $PB_DIR ]; then
  cd $PB_DIR
  git pull
  git checkout $PB_BRANCH
else
  git clone https://github.com/efforg/privacybadger $PB_DIR
  git checkout $PB_BRANCH
fi

# change to the badger-sett repository
cd $DIR

# figure out whether we need to pull
UPSTREAM=${1:-'@{u}'}
LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse "$UPSTREAM")

if [ $LOCAL = $REMOTE ]; then
  echo "Local repository up-to-date."
else
  # update the repository to avoid merge conflicts later
  echo "Pulling latest version of repository..."
  git pull
fi

# build the new docker image
echo "Building Docker container..."

# pass in the current user's uid and gid so that the scan can be run with the
# same bits in the container (this prevents permissions issues in the out/ folder)
if ! docker build --build-arg UID=$(id -u "$USER") \
    --build-arg GID=$(id -g "$USER") \
    --build-arg UNAME=$USER -t badger-sett . ; then
  echo "Docker build failed."
  exit 1;
fi

# create the output folder if necessary
DOCKER_OUT=$(pwd)/docker-out
mkdir -p $DOCKER_OUT

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
    -v $DOCKER_OUT:/home/$USER/out:z \
    -v /dev/shm:/dev/shm \
    badger-sett "$@" ; then
  mv $DOCKER_OUT/log.txt ./
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

# Validate the output
if ! python validate.py results.json $DOCKER_OUT/results.json ; then 
  echo "Scan failed: results.json is invalid."
  exit 1
fi

# back up old results
cp results.json results-prev.json

# copy the updated results and log file out of the docker volume
mv $DOCKER_OUT/results.json $DOCKER_OUT/log.txt ./

if [ "$GIT_PUSH" != "1" ] ; then
  echo "Scan successful."
  exit 0
fi

# if the new results.json is different from the old, commit it
if [ -e $DOCKER_OUT/results.json ] && \
    [ "$(diff results.json $DOCKER_OUT/results.json)" != "" ]; then
  echo "Scan successful. Updating public repository."

  # Commit updated list to github
  git add results.json results-prev.json
  git commit -m "Update seed data: `date`"
  git push
  exit 0
else
  echo "Scan failed."
  exit 1
fi
