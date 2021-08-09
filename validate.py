#!/usr/bin/env python3

import json
import re
import sys

from collections import defaultdict

import colorama
import tldextract

# ./validate.py old.json new.json
if len(sys.argv) == 3:
    old_path = sys.argv[1]
    new_path = sys.argv[2]
# ./validate.py new.json
elif len(sys.argv) == 2:
    old_path = None
    new_path = sys.argv[1]
else:
    print("Usage: {} [BADGER_JSON_OLD] BADGER_JSON_NEW".format(sys.argv[0]))
    sys.exit(1)

if old_path:
    with open(old_path) as f:
        old_js = json.load(f)
else:
    old_js = {
        "action_map": {},
        "snitch_map": {},
    }

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
C_YELLOW = colorama.Style.BRIGHT + colorama.Fore.YELLOW
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

if blocked_bases_old:
    print("\nCount of blocked base domains went from {} to {} ({:+0.2f}%)".format(
        len(blocked_bases_old), len(blocked_bases_new),
        (len(blocked_bases_new) - len(blocked_bases_old)) / len(blocked_bases_old) * 100
    ))

newly_blocked = blocked_bases_new - blocked_bases_old
print("\n{}++{} Newly blocked domains ({}):\n".format(
    C_GREEN, C_RESET, len(newly_blocked)))
for base in sorted(newly_blocked):
    subdomains = blocked_new[base]
    cookieblocked = ""
    if base in new_js['action_map']:
        if new_js['action_map'][base]['heuristicAction'] == "cookieblock":
            cookieblocked = "{}❋{}".format(C_YELLOW, C_RESET)
    out = "  {}{}{}{}".format(cookieblocked, C_GREEN, base, C_RESET)
    if base in new_js['snitch_map']:
        sites = ", ".join(new_js['snitch_map'][base])
        sites = sites.replace(".edu", "." + C_YELLOW + "edu" + C_RESET)
        sites = sites.replace(".org", "." + C_YELLOW + "org" + C_RESET)
        out = out + " on " + sites
    print(out)
    if len(subdomains) > 1 or subdomains[0] != base:
        for y in sorted(subdomains):
            if y == base:
                continue
            out = "    • {}{}"
            if y in new_js['snitch_map']:
                out = out + " on " + ", ".join(new_js['snitch_map'][y])
            cookieblocked = ""
            if new_js['action_map'][y]['heuristicAction'] == "cookieblock":
                cookieblocked = "{}❋{}".format(C_YELLOW, C_RESET)
            print(out.format(cookieblocked, y))

no_longer_blocked = blocked_bases_old - blocked_bases_new
if no_longer_blocked:
    print("\n{}--{} No longer blocked domains ({}):\n".format(
        C_RED, C_RESET, len(no_longer_blocked)))
for base in sorted(no_longer_blocked):
    subdomains = blocked_old[base]
    out = "  {}{}{}".format(C_RED, base, C_RESET)
    if base in old_js['snitch_map']:
        out = out + " on " + ", ".join(old_js['snitch_map'][base])
    print(out)
    if len(subdomains) > 1 or subdomains[0] != base:
        for y in sorted(subdomains):
            if y == base:
                continue
            out = "    • {}"
            if y in old_js['snitch_map']:
                out = out + " on " + ", ".join(old_js['snitch_map'][y])
            print(out.format(y))

# look for common "roots" (base minus PSL TLD)
MIN_SHARED_ROOTS = 3
print_mdfp_header = True
for base in sorted(new_js['snitch_map'].keys()):
    sites = new_js['snitch_map'][base]

    # include the tracker base, sans common resource domain strings
    tracker_root = extract(base).domain
    sbr = tracker_root
    for s in ("static", "cdn", "media", "assets", "images", "img", "storage", "files", "edge", "cache", "st"):
        sbr = sbr.replace("-" + s, "").replace(s + "-", "").replace(s, "")
        # guard against removing the entire root
        if not sbr:
            sbr = tracker_root
    site_roots = [extract(site).domain for site in sites] + [sbr]

    shared_roots = [
        root for root in set(site_roots)
        if site_roots.count(root) >= MIN_SHARED_ROOTS
    ]
    # also see if sbr is found inside MIN_SHARED_ROOTS site_roots
    if sbr not in shared_roots:
        num_substr_matches = len([True for site_root in site_roots if sbr in site_root])
        if num_substr_matches >= MIN_SHARED_ROOTS:
            shared_roots.append(sbr)

    if not shared_roots:
        continue

    if print_mdfp_header:
        print("\n{}??{} MDFP candidates:\n".format(C_YELLOW, C_RESET))
        print_mdfp_header = False

    # highlight common roots
    def highlight(string, root):
        return "{}".join(
            # split preserving separator
            re.split('('+root+')', string, 1)
        ).format(C_YELLOW, C_RESET)
    formatted_sites = []
    for site in sites:
        for root in shared_roots:
            if root in site:
                site = highlight(site, root)
                break
        formatted_sites.append(site)
    formatted_base = base
    for root in shared_roots:
        if root in base:
            formatted_base = highlight(base, root)
            break

    print(" ", formatted_base, "on", ", ".join(formatted_sites))

print("")

sys.exit(0)
