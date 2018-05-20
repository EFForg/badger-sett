FROM python:3.6-stretch
FROM selenium/standalone-chrome

USER root

RUN mkdir /code
WORKDIR /code

COPY requirements.txt . 
RUN apt-get update; apt-get install -y python-pip git
RUN pip install -r requirements.txt

COPY ./* /code/
ENV BADGER_BASEDIR=/code
ENTRYPOINT ["/code/runscan.sh"]
