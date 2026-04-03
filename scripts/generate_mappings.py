#!/usr/bin/env python3
"""
Generate mapping JSON files from zones/*.yaml and geojson/*.json.

Finds geojson and zones files by country code, generates mapping keyed by
the shape property (shapeName or shapeID depending on country config).

Usage:
  python3 scripts/generate_mappings.py                  # uses geojson datestamp
  python3 scripts/generate_mappings.py --date 20260405  # force new datestamp
"""

import glob
import json
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_countries():
    """Load countries.yaml."""
    with open(os.path.join(ROOT, 'data', 'countries.yaml')) as f:
        return yaml.safe_load(f)['countries']


def load_zones(cc):
    """Load zones/{CC}.yaml."""
    path = os.path.join(ROOT, 'data', 'zones', f'{cc}.yaml')
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return yaml.safe_load(f)['zones']


def find_geojson(cc):
    """Find the geojson file for a country code. Returns (path, datestamp) or (None, None)."""
    pattern = os.path.join(ROOT, 'data', 'geojson', f'{cc}-*-geojson-*.json')
    matches = glob.glob(pattern)
    if not matches:
        return None, None
    path = matches[0]
    m = re.search(r'-(\d{8})\.json$', path)
    datestamp = m.group(1) if m else None
    return path, datestamp


def main():
    # Parse --date override
    date_override = None
    args = sys.argv[1:]
    if '--date' in args:
        idx = args.index('--date')
        if idx + 1 < len(args):
            date_override = args[idx + 1]
            print(f"Using date override: {date_override}")

    countries = load_countries()

    for country in countries:
        cc = country['code']

        zones = load_zones(cc)
        if not zones:
            print(f"  SKIP {cc}: no zones file")
            continue

        geojson_path, geojson_date = find_geojson(cc)
        if not geojson_path:
            print(f"  SKIP {cc}: no geojson file")
            continue

        # Extract adm level from geojson filename
        adm_match = re.search(r'-(adm\d+)-', os.path.basename(geojson_path))
        adm_level = adm_match.group(1) if adm_match else 'adm2'

        datestamp = date_override or geojson_date
        if not datestamp:
            print(f"  SKIP {cc}: cannot determine datestamp")
            continue

        # Build mapping: shape key -> {zone, state}
        mapping = {}
        for zone in zones:
            for shape in zone.get('shapes') or []:
                mapping[shape] = {
                    'zone': zone['code'],
                    'state': zone.get('state', ''),
                }

        # Write mapping file
        out_path = os.path.join(ROOT, 'data', 'mappings', f'{cc}-{adm_level}-mapping-{datestamp}.json')
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'w') as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)
            f.write('\n')
        print(f"  {cc}: wrote {len(mapping)} entries to {os.path.basename(out_path)}")


if __name__ == '__main__':
    main()
