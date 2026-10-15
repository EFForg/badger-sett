#!/usr/bin/env python3

import argparse
import json

from glob import glob

from lib.basedomain import extract
from lib.mdfp import is_mdfp_first_party


def is_first_party(site_domain, domain):
    if domain == site_domain or domain.endswith("." + site_domain):
        return True
    site_base = extract(site_domain).registered_domain
    domain_base = extract(domain).registered_domain
    return is_mdfp_first_party(site_base, domain_base)


def populate_stats(cookies_json):
    with open(cookies_json, 'r', encoding="utf-8") as fh:
        data = json.load(fh)

        if "site_domain" not in data or "cookies" not in data:
            return {}

        site_domain = data["site_domain"]
        #site_url = data["site_url"]
        #timed_out = data["timeout"]

        stats = {}
        data["total"] = 0

        for cookie in data["cookies"]:
            domain = cookie["domain"]
            if is_first_party(site_domain, domain):
                continue

            if domain not in stats:
                stats[domain] = 0
                data["total"] += 1

            stats[domain] += 1

            #print(site_domain, domain, cookie["name"], cookie["value"])

        #print(site_domain, site_url, len(stats.keys()), ("TIMEOUT" if timed_out else ""))
        #print()

        out = {}
        out[site_domain] = data
        return out

    return {}


def print_summary(stats_prev, stats):
    domains = set()
    timeouts = 0
    for site in stats:
        site_domain = stats[site]["site_domain"]
        if stats[site]["timeout"]:
            timeouts += 1
        for cookie in stats[site]["cookies"]:
            domain = cookie["domain"]
            if is_first_party(site_domain, domain):
                continue
            domains.add(domain)
    total = len(domains)

    domains_prev = set()
    timeouts_prev = 0
    for site in stats_prev:
        site_domain = stats_prev[site]["site_domain"]
        if stats_prev[site]["timeout"]:
            timeouts_prev += 1
        for cookie in stats_prev[site]["cookies"]:
            domain = cookie["domain"]
            if is_first_party(site_domain, domain):
                continue
            domains_prev.add(domain)
    total_prev = len(domains_prev)

    print("OVERALL", total_prev, timeouts_prev, total, timeouts,
        f"{round((total - total_prev) / total_prev * 100, 2):+}%")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('cookies_path1')
    parser.add_argument('cookies_path2')

    args = parser.parse_args()

    stats = {}
    stats2 = {}
    out = []

    for cookies_json in glob(f"{args.cookies_path1}/*.json"):
        stats = stats | populate_stats(cookies_json)

    for cookies_json in glob(f"{args.cookies_path2}/*.json"):
        stats2 = stats2 | populate_stats(cookies_json)

    for site in stats2:
        total = stats2[site]["total"]
        timeout = ("TMOUT" if stats2[site]["timeout"] else "-")
        if site in stats:
            total_prev = stats[site]["total"]
            timeout_prev = ("TMOUT" if stats[site]["timeout"] else "-")
            if total_prev == total:
                out.append((site, total_prev, timeout_prev, total, timeout))
            elif total_prev > 0:
                out.append((site, total_prev, timeout_prev, total, timeout,
                    f"{round((total - total_prev) / total_prev * 100, 2):+}%"))
            else: # total_prev == 0
                out.append((site, total_prev, timeout_prev, total, timeout))
        else: # site is missing from previous scan
            out.append((site, "-", "-", total, timeout))

    for site in stats:
        total = stats[site]["total"]
        timeout = ("TMOUT" if stats[site]["timeout"] else "-")
        if site not in stats2:
            # site is missing from newer scan
            out.append((site, total, timeout, "-", "-"))

    # sort by previous number of third-party cookie domains
    out.sort(key=lambda row: (0 if row[1] == "-" else row[1]), reverse=True)
    for line in out:
        print(*line)

    # show overall change in number of third-party cookie domains
    print_summary(stats, stats2)
