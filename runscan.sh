#!/bin/bash

# change to the right working dir
cd $HOME/badger-sett

# download the latest version of privacy badger
wget -O privacy-badger.crx https://www.eff.org/files/privacy_badger-chrome.crx

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
sudo docker build --build-arg UID=$(id -u "$USER") --build-arg GID=$(id -g "$USER") --build-arg UNAME=$USER -t badger-sett .

# back up old results
cp results.json results-prev.json

# create the output folder if necessary
DOCKER_OUT=$(pwd)/docker-out
mkdir -p $DOCKER_OUT

# Run main python scanner
echo "Running scan in Docker..."
sudo docker run -v $DOCKER_OUT:/home/$USER/out:z badger-sett

# if the new results.json is different from the old
if [ -e $DOCKER_OUT/results.json ] && [ "$(diff results.json $DOCKER_OUT/results.json)" != "" ]; then
  echo "Scan successful. Updating public repository."
  # copy the updated results and log file out of the docker volume
  mv $DOCKER_OUT/results.json $DOCKER_OUT/log.txt ./

  # Commit updated list to github
  git add results.json results-prev.json
  git commit -m "Update seed data: `date`"
  git push
  exit 0
else
  echo "Scan failed."
  exit 1
fi
