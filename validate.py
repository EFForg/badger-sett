import json
import sys

KEYS = ['action_map', 'snitch_map', 'version']

with open('results.json') as f:
    old_js = json.load(f)

with open('docker-out/results.json') as f:
    new_js = json.load(f)

for k in KEYS:
    assert k in new_js

if not len(new_js['snitch_map'].keys()):
    print("Error: Snitch map empty.")
    sys.exit(1)

if not len(new_js['action_map'].keys()):
    print("Error: Action map empty.")
    sys.exit(1)

old_keys = set(old_js['action_map'].keys())
new_keys = set(new_js['action_map'].keys())

overlap = old_keys & new_keys
print("New action map has %d new domains and dropped %d old domains" %
      (len(new_keys - overlap), len(old_keys - overlap)))

sys.exit(0)
