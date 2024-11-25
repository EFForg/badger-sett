#!/usr/bin/env python3

import os
import time
import urllib


class Blocklist:

    cache_dir = os.path.join("lib", "lists", ".cache")

    ready = False

    def _download(self, url, filename):
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req) as conn:
                data = conn.read()
        except urllib.error.HTTPError as e:
            print(f"HTTP error fetching {url}: {e.code} {e.reason}")
        except urllib.error.URLError as e:
            print(f"URL error fetching {url}: {e.reason}")
        else:
            with open(filename, 'w', encoding='utf-8') as file:
                file.write(data.decode('utf-8'))

    def fetch(self, url, filename):
        os.makedirs(self.cache_dir, exist_ok=True)

        if not os.path.isfile(filename):
            self._download(url, filename)
        # redownload if older than 24 hours
        elif (time.time() - os.path.getmtime(filename)) / 3600 > 24:
            # first remove (back up) the file so that if downloading fails,
            # we know something went wrong
            os.replace(filename, filename + ".bak")
            self._download(url, filename)
