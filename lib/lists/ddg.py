#!/usr/bin/env python3

import json
import os

from lib.basedomain import extract
from lib.lists.blocklist import Blocklist


class DDG(Blocklist):

    ready = False
    bases = set()
    bases_unblocked = set()
    domains = set()
    prevalences = {}

    test_entities = ("Ad Company", "Ad Company Example", "EFF Test Trackers",
                     "Test Site for Tracker Blocking")

    def ingest(self, domain, conf):
        # ignore test entities
        if conf.get("owner", []).get("name") in self.test_entities:
            return

        base = extract(domain).registered_domain
        if not base:
            base = domain
        self.bases.add(base)

        # DDG matching logic:
        # https://github.com/duckduckgo/tracker-blocklists/blob/main/web/EXAMPLES.md

        if conf.get("default") == "ignore":
            # if the default rule is "ignore" and there are no "block" rules
            if not any(True for rule in conf.get("rules", []) if rule.get("action") == "block"):
                # count the eTLD+1 as unblocked
                self.bases_unblocked.add(base)

        self.domains.add(domain)
        self.prevalences[domain] = conf["prevalence"]

    def __init__(self):
        url = "https://staticcdn.duckduckgo.com/trackerblocking/v6/current/extension-tds.json"
        filename = os.path.join(self.cache_dir, "ddg-tds.json")

        self.fetch(url, filename)

        try:
            with open(filename, encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"WARNING Failed to open {filename}")
            return

        for domain, conf in data["trackers"].items():
            self.ingest(domain, conf)

        self.ready = True
