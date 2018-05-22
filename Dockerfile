FROM python:3.6-stretch
FROM selenium/standalone-chrome

USER root

RUN mkdir /code
WORKDIR /code

RUN apt-get update; apt-get install -y python3-pip

COPY requirements.txt . 
RUN pip3 install -r requirements.txt

COPY . /code/badger-sett
ENV OUTPATH=/code/badger-sett/out
RUN mkdir -p $OUTPATH

ENTRYPOINT ["/code/badger-sett/docker-entry.sh"]
