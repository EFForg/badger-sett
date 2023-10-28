#!/usr/bin/env python3

import colorama

from collections import Counter


C_YELLOW = colorama.Style.BRIGHT + colorama.Fore.YELLOW
C_RESET = colorama.Style.RESET_ALL

# TODO this works for normally distributed data, but is our data is normally distributed?
def outliers(data):
    mean = sum(data) / (1.0 * len(data))
    var = sum((data[i] - mean)**2 for i in range(0, len(data))) / (1.0 * len(data))
    std = var**0.5
    # three standard deviations
    return [data[i] for i in range(0, len(data)) if abs(data[i] - mean) > 2.58 * std]

def print_warnings(snitch_map):
    counters = Counter(site for sites in snitch_map.values() for site in sites)
    sample_size = int(sum(1 for _ in counters) / 200) # 0.5%

    suspicious_sites = counters.most_common(len(
        outliers(list(count for site, count in counters.most_common(sample_size)))))

    if suspicious_sites:
        print(f"\n{C_YELLOW}??{C_RESET} Suspiciously tracker-rich sites:\n")
        # first print the suspicious sites
        for site, count in suspicious_sites:
            print(f"  {C_YELLOW}{count}{C_RESET} domains on {site}")
        # and then print a few following sites for context
        for site, count in list(counters.most_common(len(suspicious_sites) + 5))[len(suspicious_sites):]:
            print(f"  {count} domains on {site}")
        print("\nYou might want to redo the merge with "
              "--load-data-ignore-sites=" + ",".join(site for site, count in suspicious_sites))
