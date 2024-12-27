#!/usr/bin/env python3

import json
import os
import urllib

from lib.basedomain import extract
from lib.lists.blocklist import Blocklist


class Ghostery(Blocklist):

    bases = set()
    bases_unblocked = set()
    domains = set() # TODO unused

    blocked_categories = ("advertising", "site_analytics", "pornvertising")

    def __init__(self):
        filename = os.path.join(self.cache_dir, "ghostery-trackerdb.json")
        expire_hrs = 168 # weekly expiration

        if not self.exists_and_unexpired(filename, expire_hrs):
            url = "https://github.com/ghostery/trackerdb/releases/latest"
            with urllib.request.urlopen(
                    urllib.request.Request(url, method='HEAD')) as conn:
                version = conn.geturl().rpartition('/')[-1]

            url = ("https://github.com/ghostery/trackerdb/releases"
                f"/download/{version}/trackerdb.json")
            self.fetch(url, filename, expire_cache_hrs=expire_hrs)

        try:
            with open(filename, encoding='utf-8') as file:
                data = json.load(file)
        except FileNotFoundError:
            print(f"WARNING Failed to open {filename}")
            return

        for name in data['patterns']:
            for domain in data['patterns'][name]['domains']:
                base = extract(domain).registered_domain or domain
                self.bases.add(base)

                if data['patterns'][name]['category'] not in self.blocked_categories:
                    self.bases_unblocked.add(base)

                self.domains.add(domain)

        self.ready = True
