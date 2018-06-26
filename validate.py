#!/usr/bin/env python3
import json
import sys
import os

# Use: ./validate.py old.json new.json
KEYS = ['action_map', 'snitch_map', 'version']
old_path = sys.argv[1]
new_path = sys.argv[2]

# make sure the files exist
assert os.path.isfile(old_path)
assert os.path.isfile(new_path)

with open(old_path) as f:
    old_js = json.load(f)

with open(new_path) as f:
    new_js = json.load(f)

# make sure new JSON is not the same as old JSON
assert old_js != new_js

# make sure the JSON is structured correctly
for k in KEYS:
    assert k in new_js

# make sure there is data in the maps
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
