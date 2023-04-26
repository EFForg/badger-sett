#!/usr/bin/env python3

import tldextract


_extract = None

def extract(domain):
    global _extract

    # lazy init
    if not _extract:
        _extract = tldextract.TLDExtract(cache_dir=False, include_psl_private_domains=True)

    return _extract(domain)
