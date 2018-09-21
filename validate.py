#!/usr/bin/env python3
import json
import sys
import os

from collections import defaultdict

import colorama
import tldextract

# Use: ./validate.py old.json new.json
old_path = sys.argv[1]
new_path = sys.argv[2]

# make sure the files exist
assert os.path.isfile(old_path)
assert os.path.isfile(new_path)

with open(old_path) as f:
    old_js = json.load(f)

with open(new_path) as f:
    new_js = json.load(f)

# make sure new JSON is not the same as old JSON
assert old_js != new_js

# make sure the JSON is structured correctly
for k in ['action_map', 'snitch_map']:
    assert k in new_js

# make sure there is data in the maps
if not new_js['snitch_map'].keys():
    print("Error: Snitch map empty.")
    sys.exit(1)

if not new_js['action_map'].keys():
    print("Error: Action map empty.")
    sys.exit(1)

old_keys = set(old_js['action_map'].keys())
new_keys = set(new_js['action_map'].keys())

overlap = old_keys & new_keys
print("New action map has %d new domains and dropped %d old domains" %
      (len(new_keys - overlap), len(old_keys - overlap)))

colorama.init()
C_GREEN = colorama.Style.BRIGHT + colorama.Fore.GREEN
C_RED = colorama.Style.BRIGHT + colorama.Fore.RED
C_RESET = colorama.Style.RESET_ALL

extract = tldextract.TLDExtract(cache_file=False)

BLOCKED = ("block", "cookieblock")

blocked_old = defaultdict(list)
for domain in old_js['action_map'].keys():
    if old_js['action_map'][domain]['heuristicAction'] not in BLOCKED:
        continue

    base = extract(domain).registered_domain
    blocked_old[base].append(domain)

blocked_new = defaultdict(list)
for domain in new_js['action_map'].keys():
    if new_js['action_map'][domain]['heuristicAction'] not in BLOCKED:
        continue

    base = extract(domain).registered_domain
    blocked_new[base].append(domain)

blocked_bases_old = set(blocked_old.keys())
blocked_bases_new = set(blocked_new.keys())

newly_blocked = blocked_bases_new - blocked_bases_old
print("\n{}++{} Newly blocked domains ({}):\n".format(
    C_GREEN, C_RESET, len(newly_blocked)))
for base in sorted(newly_blocked):
    subdomains = blocked_new[base]
    out = "  {}{}{}".format(C_GREEN, base, C_RESET)
    if len(subdomains) > 1:
        out = out + " ({})".format(len(subdomains))
    print(out)
    if len(subdomains) > 1 or subdomains[0] != base:
        for y in sorted(subdomains):
            print("    • {}".format(y))

no_longer_blocked = blocked_bases_old - blocked_bases_new
print("\n{}--{} No longer blocked domains ({}):\n".format(
    C_RED, C_RESET, len(no_longer_blocked)))
for base in sorted(no_longer_blocked):
    subdomains = blocked_old[base]
    out = "  {}{}{}".format(C_RED, base, C_RESET)
    if len(subdomains) > 1:
        out = out + " ({})".format(len(subdomains))
    print(out)
    if len(subdomains) > 1 or subdomains[0] != base:
        for y in sorted(subdomains):
            print("    • {}".format(y))

print("")

sys.exit(0)
