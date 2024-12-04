#!/usr/bin/env python3

import json
import os

from collections import defaultdict

from lib.basedomain import extract
from lib.lists.blocklist import Blocklist


class Disconnect(Blocklist):

    categories = defaultdict(set)
    bases = []
    bases_unblocked = []

    def process_entity(self, category, entity):
        for name in entity:
            for url, domains in entity[name].items():
                if not url.startswith("http") and not isinstance(domains, list):
                    continue
                for domain in domains:
                    base = extract(domain).registered_domain
                    if not base:
                        base = domain
                    self.categories[category].add(base)

    def __init__(self):
        url = "https://services.disconnect.me/disconnect-plaintext.json"
        filename = os.path.join(self.cache_dir, "disconnect-plaintext.json")

        self.fetch(url, filename, expire_cache_hrs=168) # weekly expiration

        try:
            with open(filename, encoding='utf-8') as file:
                data = json.load(file)
        except FileNotFoundError:
            print(f"WARNING Failed to open {filename}")
            return

        for category in data['categories']:
            for entity in data['categories'][category]:
                self.process_entity(category, entity)

        self.bases = [base for domains in self.categories.values() for base in domains]
        # TODO ignore Content category domains when comparing what we're not blocking
        self.bases_unblocked = list(self.categories["Content"])

        self.ready = True
