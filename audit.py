from collections import Counter
import git
import json
import re

def count_domain_blocks():
    repo = git.Repo('./')
    old_maps = {}

    # load old map data
    for c in repo.iter_commits('master'):
        if re.match('Update seed data: \d+\.\d+\.\d+', c.message):
            repo.git.checkout(c.hexsha)
            with open('results.json') as f:
                js = json.load(f)
            if 'version' in js:
                old_maps[js['version']] = js

    # count number of times each domain has been blocked
    ctr = Counter()
    for m in old_maps.values():
        for domain, data in m['action_map'].items():
            if data['heuristicAction'] in ['block', 'cookieblock']:
                ctr[domain] += 1

    return ctr

# Find domains that are blocked now but have never been blocked before
def count_new_blocks(data):
    blocked = [d for d, v in data['action_map'].items()
               if v['heuristicAction'] in ['block', 'cookieblock']]
    ctr = count_domain_blocks()
    new = [d for d in blocked if d not in ctr]
    return new
