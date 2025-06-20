ARG BROWSER=firefox

FROM python:3.11
FROM selenium/standalone-${BROWSER}

ARG BROWSER=firefox

ARG UID
ARG GID
ARG UNAME

USER root

RUN apt-get update; apt-get install -y python3-pip git

# install Chrome for Testing
RUN if [ "$BROWSER" = chrome ]; then \
  apt-get install -y npm xvfb; \
  npx @puppeteer/browsers install chrome@stable; \
  npx @puppeteer/browsers install chromedriver@stable; \
  CHROME_BINARY=$(npx @puppeteer/browsers list | head -n 1 | cut -d ' ' -f 3); \
  CHROMEDRIVER_BINARY=$(npx @puppeteer/browsers list | tail -n 1 | cut -d ' ' -f 3); \
  ln -sf "$CHROME_BINARY" /usr/bin/google-chrome; \
  ln -sf "$CHROMEDRIVER_BINARY" /usr/bin/chromedriver; \
fi

RUN if [ $(getent group $GID) ]; then \
  old_group=$(getent group $GID | cut -d: -f1); \
  groupmod -n $UNAME $old_group; \
else \
  echo "Creating group $UNAME ($GID)"; \
  groupadd -g $GID $UNAME; \
fi

RUN if [ $(getent passwd $UID) ]; then \
  old_uname=$(getent passwd $UID | cut -d: -f1); \
  usermod -l $UNAME -g $GID -m -d /home/$UNAME -s /bin/bash $old_uname; \
else \
  echo "Creating user $UNAME ($UID:$GID)"; \
  useradd -ms /bin/bash -u $UID -g $GID $UNAME; \
fi

USER $UNAME
ENV USER=$UNAME
ENV HOME=/home/$USER
ENV OUTPATH=$HOME/out/
ENV PBPATH=$HOME/privacybadger/
ENV EXTENSIONS=$HOME/parallel-extensions/

WORKDIR $HOME

COPY requirements.txt .
USER root
RUN pip3 install -r requirements.txt
USER $UNAME

COPY crawler.py docker-entry.sh $HOME/
COPY lib $HOME/lib
COPY .git $HOME/.git
COPY domain-lists $HOME/domain-lists
COPY privacybadger $PBPATH
COPY parallel-extensions $EXTENSIONS

USER root
RUN chown -R $USER:$USER $PBPATH $HOME/.git
USER $UNAME
RUN mkdir -p $OUTPATH

ENTRYPOINT ["./docker-entry.sh"]
CMD []
