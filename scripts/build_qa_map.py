#!/usr/bin/env python3
"""
Build Qatar's map: one shape for the whole country (one national timetable,
zone QA01), named "Qatar" (shown as the place).

Source: geoBoundaries QAT ADM0 (ODbL 1.0), simplified to ~50 m.

Usage (needs shapely):
  python3 scripts/build_qa_map.py geoBoundaries-QAT-ADM0.geojson 20261103
"""

import json
import os
import sys

from shapely.geometry import mapping, shape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rounded(obj):
    if isinstance(obj, float):
        return round(obj, 5)
    if isinstance(obj, (list, tuple)):
        return [rounded(x) for x in obj]
    if isinstance(obj, dict):
        return {k: rounded(v) for k, v in obj.items()}
    return obj


def main():
    base_path, date = sys.argv[1], sys.argv[2]
    base = json.load(open(base_path))
    geom = shape(base['features'][0]['geometry']).buffer(0).simplify(0.0005, preserve_topology=True)
    feature = {'type': 'Feature',
               'properties': {'shapeName': 'Qatar', 'shapeGroup': 'QAT', 'shapeType': 'ADM0'},
               'geometry': rounded(mapping(geom))}
    out = os.path.join(ROOT, 'data', 'geojson', f'QA-adm0-geojson-{date}.json')
    with open(out, 'w') as fh:
        json.dump({'type': 'FeatureCollection', 'features': [feature]}, fh, separators=(',', ':'))
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
