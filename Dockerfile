FROM python:3.6-jessie
#FROM selenium/standalone-chrome
FROM selenium/standalone-firefox
ARG UID
ARG GID
ARG UNAME

USER root

RUN apt-get update; apt-get install -y python3-pip

RUN if [ $(getent group $GID) ]; then \
  old_group=$(getent group $GID | cut -d: -f1); \
  groupmod -n $UNAME $old_group; \
else \
  groupadd -g $GID $UNAME; \
fi

RUN if [ $(getent passwd $UID) ]; then \
  old_uname=$(getent passwd $UID | cut -d: -f1); \
  usermod -l $UNAME -m -d /home/$UNAME -s /bin/bash $old_uname; \
else \
  useradd -ms /bin/bash -u $UID $UNAME; \
fi

USER $UNAME
ENV USER=$UNAME

WORKDIR /home/$USER

COPY requirements.txt .
RUN pip3 install --user -r requirements.txt

COPY crawler.py docker-entry.sh /home/$USER/
COPY privacybadger /home/$USER/privacybadger
ENV OUTPATH=/home/$USER/out
ENV EXTPATH=/home/$USER/privacybadger/src
RUN mkdir -p $OUTPATH

ENTRYPOINT ["./docker-entry.sh"]
