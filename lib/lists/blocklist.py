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

    def exists_and_unexpired(self, filename, expire_cache_hrs):
        if not os.path.isfile(filename):
            return False

        time_diff = time.time() - os.path.getmtime(filename)
        if time_diff / 3600 > expire_cache_hrs:
            return False

        return True

    def fetch(self, url, filename, expire_cache_hrs=24):
        os.makedirs(self.cache_dir, exist_ok=True)

        if not self.exists_and_unexpired(filename, expire_cache_hrs):
            if os.path.isfile(filename):
                # first remove (back up) the file so that if downloading fails,
                # we know something went wrong
                os.replace(filename, filename + ".bak")

            self._download(url, filename)
