#!/usr/bin/env python3

import argparse
import json
import sys

from collections import defaultdict

import colorama

from lib.basedomain import extract

from lib.lists.adblocker import Adblocker
from lib.lists.ddg import DDG
from lib.lists.disconnect import Disconnect
from lib.lists.ghostery import Ghostery

from lib.linters.mdfp import print_warnings as flag_potential_mdfp_domains
from lib.linters.unblocked import print_warnings as list_unblocked_canvas_fingerprinters
from lib.linters.site_outliers import print_warnings as list_suspicious_site_domains


ap = argparse.ArgumentParser()
ap.add_argument('old_path', nargs='?')
ap.add_argument('new_path')
ap.add_argument('--badger-only', action='store_true', default=False)
args = ap.parse_args()

if args.old_path:
    with open(args.old_path, encoding='utf-8') as f:
        old_js = json.load(f)
else:
    old_js = {
        "action_map": {},
        "snitch_map": {},
    }

with open(args.new_path, encoding='utf-8') as f:
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

adblocker = Adblocker()
ddg = DDG()
disconnect = Disconnect()
ghostery = Ghostery()

ddg_blocked = ddg.bases - ddg.bases_unblocked
disconnect_blocked = disconnect.bases - disconnect.bases_unblocked
ghostery_blocked = ghostery.bases - ghostery.bases_unblocked

combined_blocked = ddg_blocked | disconnect_blocked | ghostery_blocked
combined_blocked_with_adblocker_lists = adblocker.bases | combined_blocked

# warn when BADGER_JSON_NEW is close to or exceeds QUOTA_BYTES
size_bytes = len(json.dumps(new_js))
if size_bytes >= (5242880 / 100 * 80):
    size_mb = round(size_bytes / 1024 / 1024, 2)
    print(f"{C_RED}WARNING{C_RESET}: {args.new_path} serializes to {size_mb} MB\n")

old_keys = set(old_js['action_map'].keys())
new_keys = set(new_js['action_map'].keys())

overlap = old_keys & new_keys
# pylint: disable-next=consider-using-f-string
print("New action map has %d new domains and dropped %d old domains\n" %
      (len(new_keys - overlap), len(old_keys - overlap)))

blocked_old = defaultdict(list)
for domain in old_js['action_map'].keys():
    base = extract(domain).registered_domain
    if not base:
        base = domain
    if base in old_js['snitch_map']:
        if len(old_js['snitch_map'][base]) >= 3:
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
    if base in new_js['snitch_map']:
        if len(new_js['snitch_map'][base]) >= 3:
            blocked_new[base].append(domain)
    else:
        # TODO happens with s3.amazonaws.com, why?
        print(f"Failed to find {base} (eTLD+1 of {domain}) in snitch_map")

blocked_bases_old = set(blocked_old.keys())
blocked_bases_new = set(blocked_new.keys())

if args.badger_only:
    badger_only_new = blocked_bases_new - combined_blocked_with_adblocker_lists
    if blocked_bases_old:
        badger_only_old = blocked_bases_old - combined_blocked_with_adblocker_lists

if blocked_bases_old:
    # pylint: disable-next=consider-using-f-string
    print("\nCount of blocked base domains went from {} to {} ({:+0.2f}%)".format(
        len(blocked_bases_old), len(blocked_bases_new),
        (len(blocked_bases_new) - len(blocked_bases_old)) / len(blocked_bases_old) * 100
    ))

newly_blocked = blocked_bases_new - blocked_bases_old
print(f"\n{C_GREEN}++{C_RESET} Newly blocked domains ({len(newly_blocked)}):\n")
for base in sorted(newly_blocked):
    if args.badger_only:
        if base not in badger_only_new:
            continue

    otherlists = ""
    if not args.badger_only:
        otherlists = "    "
        if base in adblocker.bases or base in ddg.bases or base in disconnect.bases or base in ghostery.bases:
            otherlists = "".join((
                "⊙" if base in adblocker.bases else " ",
                f"{C_YELLOW}⊙{C_RESET}" if base in ddg.bases_unblocked else (
                    "⊙" if base in ddg.bases else " "),
                f"{C_YELLOW}⊙{C_RESET}" if base in disconnect.bases_unblocked else (
                    "⊙" if base in disconnect.bases else " "),
                f"{C_YELLOW}⊙{C_RESET}" if base in ghostery.bases_unblocked else (
                    "⊙" if base in ghostery.bases else " ")))
    cookieblocked = ""
    if base in new_js['action_map']:
        if new_js['action_map'][base]['heuristicAction'] == "cookieblock":
            cookieblocked = f"{C_YELLOW}❋{C_RESET}"
    out = f" {otherlists} {cookieblocked}{C_GREEN}{base}{C_RESET}"
    if base in new_js['snitch_map']:
        sites = ", ".join(new_js['snitch_map'][base])
        sites = sites.replace(".edu", "." + C_YELLOW + "edu" + C_RESET)
        sites = sites.replace(".org", "." + C_YELLOW + "org" + C_RESET)
        sites = sites.replace(".gov", "." + C_RED + "gov" + C_RESET)
        sites = sites.replace(".mil", "." + C_RED + "mil" + C_RESET)
        out = out + " on " + sites
    print(out)

    subdomains = blocked_new[base]
    if len(subdomains) > 1 or subdomains[0] != base:
        for y in sorted(subdomains):
            if y == base:
                continue
            out = "        • {}{}" if not args.badger_only else "    • {}{}"
            if y in new_js['snitch_map']:
                out = out + " on " + ", ".join(new_js['snitch_map'][y])
            cookieblocked = ""
            # cookieblocked if it or any parent domain up to base is cookieblocked
            domain_parts = y.split('.')
            exploded_subdomains = (s for s in (
                    '.'.join(domain_parts[idx:])
                    for idx, _ in enumerate(domain_parts))
                if len(s) >= len(base))
            if any(sub for sub in exploded_subdomains
                   if new_js['action_map'].get(sub, {}).get('heuristicAction', "") == "cookieblock"):
                cookieblocked = f"{C_YELLOW}❋{C_RESET}"
            print(out.format(cookieblocked, y))

no_longer_blocked = blocked_bases_old - blocked_bases_new
if no_longer_blocked:
    print(f"\n{C_RED}--{C_RESET} No longer blocked domains ({len(no_longer_blocked)}):\n")
for base in sorted(no_longer_blocked):
    if args.badger_only:
        if base not in badger_only_old:
            continue

    otherlists = ""
    if not args.badger_only:
        otherlists = "    "
        if base in adblocker.bases or base in ddg.bases or base in disconnect.bases or base in ghostery.bases:
            otherlists = "".join((
                "⊙" if base in adblocker.bases else " ",
                f"{C_YELLOW}⊙{C_RESET}" if base in ddg.bases_unblocked else (
                    "⊙" if base in ddg.bases else " "),
                f"{C_YELLOW}⊙{C_RESET}" if base in disconnect.bases_unblocked else (
                    "⊙" if base in disconnect.bases else " "),
                f"{C_YELLOW}⊙{C_RESET}" if base in ghostery.bases_unblocked else (
                    "⊙" if base in ghostery.bases else " ")))
    out = f" {otherlists} {C_RED}{base}{C_RESET}"
    if base in old_js['snitch_map']:
        out = out + " on " + ", ".join(old_js['snitch_map'][base])
    print(out)

    subdomains = blocked_old[base]
    if len(subdomains) > 1 or subdomains[0] != base:
        for y in sorted(subdomains):
            if y == base:
                continue
            out = "        • {}" if not args.badger_only else "    • {}"
            if y in old_js['snitch_map']:
                out = out + " on " + ", ".join(old_js['snitch_map'][y])
            print(out.format(y))

flag_potential_mdfp_domains(new_js['snitch_map'])

list_unblocked_canvas_fingerprinters(new_js)

list_suspicious_site_domains(new_js['snitch_map'])

print("")

sys.exit(0)
