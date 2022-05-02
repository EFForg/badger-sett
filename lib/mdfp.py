#!/usr/bin/env python3

import re

import colorama


C_YELLOW = colorama.Style.BRIGHT + colorama.Fore.YELLOW
C_RESET = colorama.Style.RESET_ALL

def get_shared_base_root(base, extract):
    tracker_root = extract(base).domain
    if not tracker_root:
        tracker_root = base.partition('.')[0]
    sbr = tracker_root
    for s in ("static", "cdn", "media", "assets", "images", "img", "storage", "files", "edge", "cache", "st"):
        sbr = sbr.replace("-" + s, "").replace(s + "-", "").replace(s, "")
        # guard against removing the entire root
        if not sbr:
            sbr = tracker_root
    return sbr

def get_site_roots(sites, extract):
    site_roots = []

    for site in sites:
        site_root = extract(site).domain
        if not site_root:
            site_root = site.partition('.')[0]
        site_roots.append(site_root)

    return site_roots

def get_shared_roots(site_roots, sbr):
    MIN_SHARED_ROOTS = 3

    shared_roots = [
        root for root in set(site_roots)
        if site_roots.count(root) >= MIN_SHARED_ROOTS
    ] if len(site_roots) <= 12 else []

    # also see if sbr is found inside MIN_SHARED_ROOTS site_roots
    if sbr not in shared_roots:
        num_substr_matches = len([True for site_root in site_roots if sbr in site_root])
        if num_substr_matches >= MIN_SHARED_ROOTS:
            shared_roots.append(sbr)

    # remove any one and two character roots
    shared_roots = [s for s in shared_roots if len(s) > 2]

    return shared_roots

def highlight_common_roots(base, sites, shared_roots):
    def highlight(string, root):
        return "{}".join(
            # split preserving separator
            re.split('('+root+')', string, 1)
        ).format(C_YELLOW, C_RESET)

    formatted_sites = []
    num_other_sites = 0

    for site in sites:
        for root in shared_roots:
            if root in site:
                site = highlight(site, root)
                num_other_sites -= 1
                formatted_sites.append(site)
                break
        num_other_sites += 1

    formatted_base = base
    for root in shared_roots:
        if root in base:
            formatted_base = highlight(base, root)
            break

    return formatted_base, formatted_sites, num_other_sites

def flag_potential_mdfp_domains(snitch_map, extract):
    """Looks for and warns about common "roots" (base minus PSL TLD).

    :param snitch_map: Privacy Badger snitch map
    :param extract: instance of tldextract.TLDExtract
    """
    print_mdfp_header = True

    for base in sorted(snitch_map.keys()):
        site_roots = get_site_roots(snitch_map[base], extract)

        # include the tracker base, sans common resource domain strings
        sbr = get_shared_base_root(base, extract)
        site_roots.append(sbr)

        shared_roots = get_shared_roots(site_roots, sbr)
        if not shared_roots:
            continue

        if print_mdfp_header:
            print(f"\n{C_YELLOW}??{C_RESET} MDFP candidates:\n")
            print_mdfp_header = False

        fbase, fsites, count_other = highlight_common_roots(
            base, snitch_map[base], shared_roots)

        sites = ", ".join(fsites)
        s = "s" if count_other > 1 else ""
        other_sites = f", and {count_other} other site{s}" if count_other else ""
        print(f"  {fbase} on {sites}{other_sites}")
