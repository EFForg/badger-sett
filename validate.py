#!/usr/bin/env python3

import json
import sys

from collections import defaultdict

import colorama

from lib.basedomain import extract
from lib.mdfp import flag_potential_mdfp_domains

old_path = None
new_path = None

# ./validate.py old.json new.json
if len(sys.argv) == 3:
    old_path = sys.argv[1]
    new_path = sys.argv[2]
# ./validate.py new.json
elif len(sys.argv) == 2:
    new_path = sys.argv[1]
else:
    print(f"Usage: {sys.argv[0]} [BADGER_JSON_OLD] BADGER_JSON_NEW")
    sys.exit(1)

if old_path:
    with open(old_path, encoding='utf-8') as f:
        old_js = json.load(f)
else:
    old_js = {
        "action_map": {},
        "snitch_map": {},
    }

with open(new_path, encoding='utf-8') as f:
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

colorama.init()
C_GREEN = colorama.Style.BRIGHT + colorama.Fore.GREEN
C_RED = colorama.Style.BRIGHT + colorama.Fore.RED
C_YELLOW = colorama.Style.BRIGHT + colorama.Fore.YELLOW
C_RESET = colorama.Style.RESET_ALL

# warn when BADGER_JSON_NEW is close to or exceeds QUOTA_BYTES
size_bytes = len(json.dumps(new_js))
if size_bytes >= (5242880 / 100 * 80):
    size_mb = round(size_bytes / 1024 / 1024, 2)
    print(f"{C_RED}WARNING{C_RESET}: {new_path} serializes to {size_mb} MB\n")

old_keys = set(old_js['action_map'].keys())
new_keys = set(new_js['action_map'].keys())

overlap = old_keys & new_keys
# pylint: disable-next=consider-using-f-string
print("New action map has %d new domains and dropped %d old domains\n" %
      (len(new_keys - overlap), len(old_keys - overlap)))

BLOCKED = ("block", "cookieblock")

blocked_old = defaultdict(list)
for domain in old_js['action_map'].keys():
    if old_js['action_map'][domain]['heuristicAction'] not in BLOCKED:
        continue

    base = extract(domain).registered_domain
    if not base:
        base = domain
    blocked_old[base].append(domain)

new_domains = defaultdict(list)
blocked_new = defaultdict(list)
for domain in new_js['action_map'].keys():
    base = extract(domain).registered_domain
    if not base:
        # IP address, a no-dots string (Privacy Badger bug), or
        # https://github.com/john-kurkowski/tldextract/issues/178
        print(f"Failed to extract base domain for {domain}")
        base = domain
    new_domains[base].append(domain)
    if new_js['action_map'][domain]['heuristicAction'] in BLOCKED:
        blocked_new[base].append(domain)

blocked_bases_old = set(blocked_old.keys())
blocked_bases_new = set(blocked_new.keys())

if blocked_bases_old:
    # pylint: disable-next=consider-using-f-string
    print("\nCount of blocked base domains went from {} to {} ({:+0.2f}%)".format(
        len(blocked_bases_old), len(blocked_bases_new),
        (len(blocked_bases_new) - len(blocked_bases_old)) / len(blocked_bases_old) * 100
    ))

newly_blocked = blocked_bases_new - blocked_bases_old
print(f"\n{C_GREEN}++{C_RESET} Newly blocked domains ({len(newly_blocked)}):\n")
for base in sorted(newly_blocked):
    subdomains = blocked_new[base]
    cookieblocked = ""
    if base in new_js['action_map']:
        if new_js['action_map'][base]['heuristicAction'] == "cookieblock":
            cookieblocked = f"{C_YELLOW}❋{C_RESET}"
    out = f"  {cookieblocked}{C_GREEN}{base}{C_RESET}"
    if base in new_js['snitch_map']:
        sites = ", ".join(new_js['snitch_map'][base])
        sites = sites.replace(".edu", "." + C_YELLOW + "edu" + C_RESET)
        sites = sites.replace(".org", "." + C_YELLOW + "org" + C_RESET)
        sites = sites.replace(".gov", "." + C_RED + "gov" + C_RESET)
        sites = sites.replace(".mil", "." + C_RED + "mil" + C_RESET)
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
                cookieblocked = f"{C_YELLOW}❋{C_RESET}"
            print(out.format(cookieblocked, y))

no_longer_blocked = blocked_bases_old - blocked_bases_new
if no_longer_blocked:
    print(f"\n{C_RED}--{C_RESET} No longer blocked domains ({len(no_longer_blocked)}):\n")
for base in sorted(no_longer_blocked):
    subdomains = blocked_old[base]
    out = f"  {C_RED}{base}{C_RESET}"
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

flag_potential_mdfp_domains(new_js['snitch_map'], extract)

# list unblocked canvas fingerprinters
# https://github.com/EFForg/privacybadger/issues/1527
if 'tracking_map' in new_js and 'fp_scripts' in new_js:
    print_canvas_header = True

    for domain in sorted(new_js['fp_scripts'], key=lambda d: extract(d).registered_domain or d):
        already_known_hosts = (
            'cdnjs.cloudflare.com',
            'cdn.jsdelivr.net',
            'd1af033869koo7.cloudfront.net',
            'd38xvr37kwwhcm.cloudfront.net',
            'd.alicdn.com',
            'fp-cdn.azureedge.net',
            'gadasource.storage.googleapis.com',
            'sdtagging.azureedge.net',
        )
        if domain in already_known_hosts:
            continue

        base = extract(domain).registered_domain or domain

        if len(new_js['snitch_map'][base]) < 3: # TRACKING_THRESHOLD
            continue

        if new_js['action_map'][base]['heuristicAction'] != "cookieblock":
            if domain not in new_js['action_map']:
                continue
            if new_js['action_map'][domain]['heuristicAction'] != "cookieblock":
                continue

        if print_canvas_header:
            print(f"\n{C_YELLOW}??{C_RESET} Unblocked canvas fingerprinters:\n")
            print_canvas_header = False

        domain_fmt = f"{C_YELLOW}{domain}{C_RESET}"
        print(f"  {domain_fmt} on", ", ".join(new_js['tracking_map'][base].keys()))

        for script_path in new_js['fp_scripts'][domain]:
            print(f"   • {domain}{script_path}")

print("")

sys.exit(0)
