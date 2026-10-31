#!/usr/bin/env python3
"""
Build the whole-country monthly files from the per-zone files:

  data/prayer-times/<CC>/<ZONE>/<YYYY-MM>.json  ->  data/prayer-times/<CC>/<YYYY-MM>.json

A country file is {"<ZONE>": [entries...], ...} with each zone's entries
exactly as in its own file, so apps can download a whole country in one
request (offline use while travelling) and read a zone the same way.

Generated at deploy time (GitHub Pages workflow, Netlify build), not
committed: the per-zone files are the source, so the two can't drift.

Usage:
  python3 scripts/build_country_files.py          # all countries
  python3 scripts/build_country_files.py MY ID    # some countries
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMES = os.path.join(ROOT, 'data', 'prayer-times')
MONTH = re.compile(r'^(\d{4}-\d{2})\.json$')


def build(cc):
    country_dir = os.path.join(TIMES, cc)
    months = {}
    for zone in sorted(os.listdir(country_dir)):
        zone_dir = os.path.join(country_dir, zone)
        if not os.path.isdir(zone_dir):
            continue
        for name in os.listdir(zone_dir):
            m = MONTH.match(name)
            if m:
                months.setdefault(m.group(1), []).append(zone)
    for month, zones in sorted(months.items()):
        combined = {}
        for zone in sorted(zones):
            with open(os.path.join(country_dir, zone, f'{month}.json')) as f:
                combined[zone] = json.load(f)
        with open(os.path.join(country_dir, f'{month}.json'), 'w') as f:
            json.dump(combined, f, separators=(',', ':'), ensure_ascii=False)
    return len(months)


def main():
    wanted = {a.upper() for a in sys.argv[1:]}
    for cc in sorted(os.listdir(TIMES)):
        if os.path.isdir(os.path.join(TIMES, cc)) and (not wanted or cc in wanted):
            print(f'{cc}: {build(cc)} country files')


if __name__ == '__main__':
    main()
