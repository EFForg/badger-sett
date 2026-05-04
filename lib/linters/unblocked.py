#!/usr/bin/env python3

import subprocess
import sys

import colorama

from lib.basedomain import extract
from lib.utils import run


C_YELLOW = colorama.Style.BRIGHT + colorama.Fore.YELLOW
C_RESET = colorama.Style.RESET_ALL

# TODO refactor, don't hardcode
_pb_dir= "../privacybadger"


def load_fp_cdn_domains():
    export_js = f"""
// shim just enough for constants.js to load
globalThis.chrome = {{ runtime: {{ getURL: ()=>{{}} }} }};
const {{ default: constants }} = await import('{_pb_dir}/src/js/constants.js');
process.stdout.write(JSON.stringify(Array.from(constants.FP_CDN_DOMAINS)));"""

    try:
        cmd = ["node", "--experimental-default-type=module", f'--eval={export_js}']
        fp_cdn_domains = run(cmd)
    except subprocess.CalledProcessError as ex:
        print(ex.stderr, file=sys.stderr)
        raise ex

    return fp_cdn_domains


# https://github.com/EFForg/privacybadger/issues/1527
def print_warnings(new_js):
    if 'tracking_map' not in new_js or 'fp_scripts' not in new_js:
        return

    print_canvas_header = True

    already_known_hosts = load_fp_cdn_domains()

    for domain in sorted(new_js['fp_scripts'], key=lambda d: extract(d).registered_domain or d):
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
