#!/usr/bin/env python3

import colorama

from lib.basedomain import extract


C_YELLOW = colorama.Style.BRIGHT + colorama.Fore.YELLOW
C_RESET = colorama.Style.RESET_ALL

# https://github.com/EFForg/privacybadger/issues/1527
def print_warnings(new_js):
    if 'tracking_map' not in new_js or 'fp_scripts' not in new_js:
        return

    print_canvas_header = True

    for domain in sorted(new_js['fp_scripts'], key=lambda d: extract(d).registered_domain or d):
        already_known_hosts = (
            'd.alicdn.com',
            's3.us-west-2.amazonaws.com',
            'fp-cdn.azureedge.net',
            'sdtagging.azureedge.net',
            'cdnjs.cloudflare.com',
            'd1af033869koo7.cloudfront.net',
            'd38xvr37kwwhcm.cloudfront.net',
            'dlthst9q2beh8.cloudfront.net',
            'cdn.jsdelivr.net',
            'gadasource.storage.googleapis.com',
        )
        if domain.endswith(".awswaf.com") or domain in already_known_hosts:
            continue

        base = extract(domain).registered_domain or domain

        if len(new_js['snitch_map'].get(base, [])) < 3: # TRACKING_THRESHOLD
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
