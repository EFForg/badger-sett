#!/usr/bin/env python3

import json
import os

from collections.abc import MutableMapping

from lib.basedomain import extract
from lib.lists.blocklist import Blocklist


# https://stackoverflow.com/a/6027615
def flatten(dictionary, parent_key='', separator='_'):
    items = []
    for key, value in dictionary.items():
        new_key = parent_key + separator + key if parent_key else key
        if isinstance(value, MutableMapping):
            items.extend(flatten(value, new_key, separator).items())
        else:
            items.append((new_key, value))
    return dict(items)


class Ghostery(Blocklist):

    bases = set()
    bases_unblocked = set()
    domains = set() # TODO unused

    blocked_categories = ("advertising", "site_analytics", "pornvertising")

    def __init__(self):
        url = "https://cdn.ghostery.com/update/v4.1/bugs.json"
        filename = os.path.join(self.cache_dir, "ghostery-bugs.json")

        self.fetch(url, filename, expire_cache_hrs=168) # weekly expiration

        try:
            with open(filename, encoding='utf-8') as file:
                data = json.load(file)
        except FileNotFoundError:
            print(f"WARNING Failed to open {filename}")
            return

        # TODO review if we can ingest some domains from other pattern types, not just "host"

        # since '_' is a valid domain names character, '_' is a bad separator
        # for working with domains names; let's use ':' instead
        host_patterns_flat = flatten(data["patterns"]["host"], separator=':')

        for domain_key, bug_id in host_patterns_flat.items():
            # trim the last segment ("_$") and then reverse
            domain = ".".join(domain_key.split(":")[:-1][::-1])

            base = extract(domain).registered_domain
            if not base:
                base = domain
            self.bases.add(base)

            aid = data["bugs"][str(bug_id)]["aid"]
            category = data["apps"][str(aid)]["cat"]
            if category not in self.blocked_categories:
                self.bases_unblocked.add(base)

            self.domains.add(domain)

        self.ready = True
