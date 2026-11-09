#!/usr/bin/env python3
"""
Build Malaysia's zone map from OpenStreetMap districts, the systematic way:

  1. python3 scripts/fetch_osm_my_districts.py /tmp/MY-osm-districts.geojson
  2. python3 scripts/build_my_map.py /tmp/MY-osm-districts.geojson <YYYYMMDD>
     - renames OSM districts to the names data/zones/MY.yaml uses (ALIASES),
     - simplifies all districts together so shared borders stay shared
       (shapely coverage_simplify, about 50 m), and keeps the result small,
     - runs scripts/patch_my_zones.py for the JAKIM zones a district map can't
       express (Zon Khas, Rompin's mukims, islands, Belum/Temengor, Putrajaya),
     - writes data/geojson/MY-osm-geojson-<date>.json and
       data/mappings/MY-osm-mapping-<date>.json (district -> zone).
  3. python3 scripts/verify_data.py zones MY       (test points must pass)
  4. python3 scripts/crosscheck_my_map.py ...      (differences vs DOSM to review)

Then point countries.yaml at the new files. Old files are never edited.

District boundaries © OpenStreetMap contributors, ODbL 1.0; the built map is
published under ODbL 1.0 too. Mukims for the Rompin split: geoBoundaries MYS
ADM3, CC BY 4.0.
"""

import json
import os
import subprocess
import sys

import shapely
from shapely.geometry import mapping, shape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOLERANCE_DEG = 0.001  # about 100 m

# OSM name -> the name used in our zone mapping (JAKIM's lists).
ALIASES = {
    'Kulai': 'Kulaijaya',
    'Tangkak': 'Ledang',
    'Central Malacca': 'Melaka Tengah',
    'Central Seberang Perai': 'Seberang Perai Tengah',
    'North Seberang Perai': 'Seberang Perai Utara',
    'South Seberang Perai': 'Seberang Perai Selatan',
    'North-East': 'Timur Laut',
    'South-West': 'Barat Daya',
    'Hulu Langat': 'Ulu Langat',
    'Hulu Selangor': 'Ulu Selangor',
    'Nabawan': 'Nabawan / Persiangan',
    'Meradong': 'Maradong',
    # One OSM district for two of ours; both PRK06.
    'Larut, Matang and Selama': 'Larut dan Matang',
}

# Districts newer than our old map: zone from JAKIM's list, or the zone of
# the district they were split from.
NEW_DISTRICTS = {
    'Gedong': ('SWK07', 'Sarawak'),   # from Simunjan
    'Sebuyau': ('SWK07', 'Sarawak'),  # in JAKIM's SWK07 list
    'Lingga': ('SWK06', 'Sarawak'),   # in JAKIM's SWK06 list
    'Pantu': ('SWK06', 'Sarawak'),    # from Sri Aman
}

ATTRIBUTION = ('District boundaries © OpenStreetMap contributors (ODbL 1.0, '
               'https://www.openstreetmap.org/copyright); Rompin mukims from '
               'geoBoundaries MYS ADM3 (CC BY 4.0); JAKIM zones added by simplesolat-data.')


def main():
    raw_path, date = sys.argv[1], sys.argv[2]
    raw = json.load(open(raw_path))['features']
    names = [ALIASES.get(f['properties']['shapeName'], f['properties']['shapeName']) for f in raw]
    geoms = shapely.coverage_simplify([shape(f['geometry']).buffer(0) for f in raw], TOLERANCE_DEG)
    base = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature',
         'properties': {'shapeName': n, 'shapeGroup': 'MYS', 'shapeType': 'ADM2',
                        'osm_id': f['properties']['osm_id']},
         'geometry': mapping(g)}
        for n, g, f in zip(names, geoms, raw)]}
    tmp = os.path.join('/tmp', f'MY-osm-base-{date}.json')
    json.dump(base, open(tmp, 'w'))
    subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'patch_my_zones.py'), tmp, date, 'osm'],
                   check=True)

    # Credit travels with the file.
    out = os.path.join(ROOT, 'data', 'geojson', f'MY-osm-geojson-{date}.json')
    built = json.load(open(out))
    built = {'type': 'FeatureCollection', 'license': 'ODbL-1.0', 'attribution': ATTRIBUTION,
             'features': built['features']}
    with open(out, 'w') as fh:
        json.dump(built, fh, separators=(',', ':'))

    # Mapping: the previous mapping plus the new districts; only names in the
    # map are kept.
    prev = sorted(p for p in os.listdir(os.path.join(ROOT, 'data', 'mappings')) if p.startswith('MY-'))[-1]
    mapping_prev = json.load(open(os.path.join(ROOT, 'data', 'mappings', prev)))
    for n, (zone, state) in NEW_DISTRICTS.items():
        mapping_prev.setdefault(n, {'zone': zone, 'state': state})
    in_map = {f['properties']['shapeName'] for f in built['features']}
    missing = sorted(in_map - set(mapping_prev))
    if missing:
        raise SystemExit(f'no zone for: {missing}')
    new_mapping = {k: v for k, v in mapping_prev.items() if k in in_map}
    mp_out = os.path.join(ROOT, 'data', 'mappings', f'MY-osm-mapping-{date}.json')
    with open(mp_out, 'w') as fh:
        json.dump(new_mapping, fh, ensure_ascii=False, indent=1)
    size = os.path.getsize(out) // 1024
    print(f'wrote {out} ({size} KB, {len(built["features"])} shapes) and {mp_out} ({len(new_mapping)} names)')


if __name__ == '__main__':
    main()
