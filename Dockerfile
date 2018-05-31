FROM python:3.6-jessie
#FROM selenium/standalone-chrome
FROM selenium/standalone-firefox
ARG UID
ARG GID
ARG UNAME

USER root

RUN apt-get update; apt-get install -y python3-pip

RUN groupadd -g $GID $UNAME
RUN useradd -ms /bin/bash -u $UID -g $GID $UNAME
USER $UNAME
ENV USER=$UNAME

WORKDIR /home/$USER

COPY requirements.txt . 
RUN pip3 install --user -r requirements.txt

COPY crawler.py docker-entry.sh privacy-badger.xpi /home/$USER/
ENV OUTPATH=/home/$USER/out
RUN mkdir -p $OUTPATH

ENTRYPOINT ["./docker-entry.sh"]
