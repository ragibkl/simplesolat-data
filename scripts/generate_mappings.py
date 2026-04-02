#!/usr/bin/env python3
"""
Generate mapping JSON files from zones/*.yaml and geojson/*.json.

For each country in countries.yaml, reads the zone file to get
zone -> shapes associations, looks up state/province from geojson
features, and writes a datestamped mapping file.

Usage: python3 scripts/generate_mappings.py
"""

import json
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_zones_yaml(path):
    """Parse a zones YAML file without pyyaml."""
    zones = []
    current = {}
    in_shapes = False
    with open(path) as f:
        for line in f:
            line = line.rstrip()
            if not line or line.strip().startswith('#') or line.strip() == 'zones:':
                continue

            m = re.match(r'\s+- code:\s+(.+)', line)
            if m:
                if current:
                    zones.append(current)
                current = {'code': m.group(1), 'shapes': []}
                in_shapes = False
                continue

            if re.match(r'\s+shapes:', line):
                in_shapes = True
                continue

            if in_shapes:
                m = re.match(r'\s+- (.+)', line)
                if m:
                    current['shapes'].append(m.group(1))
                    continue
                else:
                    in_shapes = False

            m = re.match(r'\s+(\w+):\s+(.+)', line)
            if m:
                current[m.group(1)] = m.group(2)

    if current:
        zones.append(current)
    return zones


def parse_countries_yaml(path):
    """Parse countries.yaml without pyyaml."""
    countries = []
    current = {}
    with open(path) as f:
        for line in f:
            line = line.rstrip()
            if not line or line.strip().startswith('#') or line.strip() == 'countries:':
                continue
            m = re.match(r'\s+- code:\s+(.+)', line)
            if m:
                if current:
                    countries.append(current)
                current = {'code': m.group(1)}
                continue
            m = re.match(r'\s+(\w+):\s+(.+)', line)
            if m:
                current[m.group(1)] = m.group(2)
    if current:
        countries.append(current)
    return countries


def load_geojson_states(geojson_path):
    """Load geojson and build shapeName -> state/province mapping."""
    with open(geojson_path) as f:
        data = json.load(f)

    shape_states = {}
    for feat in data['features']:
        props = feat['properties']
        shape_name = props.get('shapeName', '')
        # Try to derive state from geojson properties
        # Different geojson files may have different property names
        state = props.get('shapeGroup', '')
        shape_states[shape_name] = state
    return shape_states


def main():
    countries = parse_countries_yaml(os.path.join(ROOT, 'data', 'countries.yaml'))

    for country in countries:
        cc = country['code']
        zones_path = os.path.join(ROOT, 'data', 'zones', f'{cc}.yaml')
        geojson_path = os.path.join(ROOT, country.get('geojson', ''))
        mapping_path = country.get('mapping', '')

        if not os.path.exists(zones_path):
            print(f"  SKIP {cc}: no zones file")
            continue

        zones = parse_zones_yaml(zones_path)

        # Load geojson for state info
        geojson_states = {}
        if os.path.exists(geojson_path):
            geojson_states = load_geojson_states(geojson_path)

        # Build mapping: shapeName -> {zone, state}
        mapping = {}
        for zone in zones:
            for shape in zone.get('shapes', []):
                state = zone.get('state', '')
                mapping[shape] = {
                    'zone': zone['code'],
                    'state': state,
                }

        # Write mapping file
        if mapping_path:
            out_path = os.path.join(ROOT, mapping_path)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, 'w') as f:
                json.dump(mapping, f, indent=2, ensure_ascii=False)
                f.write('\n')
            print(f"  {cc}: wrote {len(mapping)} entries to {mapping_path}")
        else:
            print(f"  {cc}: no mapping path configured")


if __name__ == '__main__':
    main()
