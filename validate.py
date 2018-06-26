#!/usr/bin/env python3
import json
import sys
import os

import colorama
import tldextract

# Use: ./validate.py old.json new.json
KEYS = ['action_map', 'snitch_map', 'version']
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
for k in KEYS:
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

blocked_old = {}
for domain in old_js['action_map'].keys():
    if old_js['action_map'][domain]['heuristicAction'] not in BLOCKED:
        continue

    base = extract(domain).registered_domain

    if base not in blocked_old:
        blocked_old[base] = []
    blocked_old[base].append(domain)

blocked_new = {}
for domain in new_js['action_map'].keys():
    if new_js['action_map'][domain]['heuristicAction'] not in BLOCKED:
        continue

    base = extract(domain).registered_domain

    if base not in blocked_new:
        blocked_new[base] = []
    blocked_new[base].append(domain)

blocked_bases_old = set(blocked_old.keys())
blocked_bases_new = set(blocked_new.keys())

print("\n{}++{} Newly blocked domains:\n".format(C_GREEN, C_RESET))
for x in sorted(blocked_bases_new - blocked_bases_old):
    print("  {}{}{} ({})".format(
        C_GREEN, x, C_RESET, len(blocked_new[x])))
    for y in sorted(blocked_new[x]):
        print("    • {}".format(y))

print("\n{}--{} No longer blocked domains:\n".format(C_RED, C_RESET))
for x in sorted(blocked_bases_old - blocked_bases_new):
    print("  {}{}{} ({})".format(
        C_RED, x, C_RESET, len(blocked_old[x])))
    for y in sorted(blocked_old[x]):
        print("    • {}".format(y))

print("")

sys.exit(0)
