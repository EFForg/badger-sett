#!/usr/bin/env python3

import os
import shutil
import tempfile
import tldextract

from datetime import datetime, timedelta

_extract = None

def extract(domain):
    global _extract

    # lazy init
    if not _extract:
        cache_dir = os.path.join(tempfile.gettempdir(), "python-tldextract")

        # expire PSL cache after one week
        elapsed_time = datetime.now() - datetime.fromtimestamp(os.stat(cache_dir).st_mtime)
        if elapsed_time >= timedelta(weeks=1):
            shutil.rmtree(cache_dir)

        _extract = tldextract.TLDExtract(cache_dir=cache_dir,
                                         include_psl_private_domains=True)

    return _extract(domain)
