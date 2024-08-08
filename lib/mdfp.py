#!/usr/bin/env python3

import json
import subprocess
import sys

from lib.utils import run

_mdfp = None
# TODO don't hardcode
_pb_dir= "../privacybadger"


def load_mdfp():
    mdfp_export_js = f"""
const {{ default: mdfp }} = await import('{_pb_dir}/src/js/multiDomainFirstParties.js');
process.stdout.write(JSON.stringify(mdfp.multiDomainFirstPartiesArray));"""

    try:
        mdfp_array = run(["node", "--experimental-default-type=module",
                          f'--eval={mdfp_export_js}'])
    except subprocess.CalledProcessError as ex:
        print(ex.stderr, file=sys.stderr)
        raise ex

    mdfp_lookup_dict = {}
    for entity_bases in json.loads(mdfp_array):
        for base in entity_bases:
            mdfp_lookup_dict[base] = entity_bases
    return mdfp_lookup_dict


def is_mdfp_first_party(base1, base2):
    global _mdfp

    # lazy init
    if not _mdfp:
        _mdfp = load_mdfp()

    return base1 in _mdfp.get(base2, [])
