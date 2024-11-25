ARG BROWSER

FROM python:3.11
FROM selenium/standalone-${BROWSER}

ARG UID
ARG GID
ARG UNAME

USER root

RUN apt-get update; apt-get install -y python3-pip git

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
RUN pip3 install --user --break-system-packages -r requirements.txt

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
