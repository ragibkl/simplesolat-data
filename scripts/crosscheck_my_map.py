#!/usr/bin/env python3
"""
Cross-check Malaysia's zone map against an independent district map, to find
places to review before a new map ships (see scripts/build_my_map.py).

Every ~5 km across Malaysia, it compares the zone our map gives with the
zone from DOSM's official district map (Department of Statistics Malaysia,
github.com/dosm-malaysia/data-open, datasets/geodata/
administrative_2_district.geojson, Malaysia Open Data Licence) and,
optionally, with an older map of ours. Differences are listed by pair of
districts with example points: border slivers are normal at this spacing;
whole areas are what to look at.

Usage (needs shapely):
  python3 scripts/crosscheck_my_map.py <dosm districts.geojson> [old geojson old mapping]
"""

import collections
import json
import os
import sys

import shapely
from shapely.geometry import shape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# DOSM name -> our mapping name, where they differ.
DOSM_ALIASES = {
    'Kulai': 'Kulaijaya', 'Tangkak': 'Ledang', 'Melaka Tengah': 'Melaka Tengah',
    'Hulu Langat': 'Ulu Langat', 'Hulu Selangor': 'Ulu Selangor',
    'Nabawan': 'Nabawan / Persiangan', 'Meradong': 'Maradong',
    'Larut Dan Matang': 'Larut dan Matang', 'Selama': 'Larut dan Matang', 'Kecil Lojing': 'Gua Musang',
    'W.P. Kuala Lumpur': 'Kuala Lumpur', 'W.P. Labuan': 'Labuan', 'W.P. Putrajaya': 'Putrajaya',
}


def current_files():
    text = open(os.path.join(ROOT, 'data', 'countries.yaml')).read()
    block = text.split('- code: MY', 1)[1].split('- code:', 1)[0]
    get = lambda key: block.split(f'{key}:', 1)[1].split()[0].split('/')[-1]
    return (os.path.join(ROOT, 'data', 'geojson', get('geojson')),
            os.path.join(ROOT, 'data', 'mappings', get('mapping')))


def zones_of(geojson_path, mapping_path, prop='shapeName', aliases=None):
    mapping = json.load(open(mapping_path))
    geoms, zones, names, unmapped = [], [], [], set()
    for f in json.load(open(geojson_path))['features']:
        name = f['properties'][prop]
        name = (aliases or {}).get(name, name)
        zone = (mapping.get(name) or {}).get('zone')
        if not zone:
            unmapped.add(name)
            continue
        geoms.append(shape(f['geometry']))
        zones.append(zone)
        names.append(name)
    if unmapped:
        print(f'  ({os.path.basename(geojson_path)}: no zone for {sorted(unmapped)})')
    tree = shapely.STRtree(geoms)

    def lookup(points):
        out = [None] * len(points)
        pi, gi = tree.query(points, predicate='within')
        for p, g in zip(pi, gi):
            out[p] = (names[g], zones[g])
        return out
    return lookup


def main():
    dosm = sys.argv[1]
    new_geo, new_map = current_files()
    ours = zones_of(new_geo, new_map)
    dosm_lookup = zones_of(dosm, new_map, prop='district', aliases=DOSM_ALIASES)
    pts = [shapely.Point(lng / 20, lat / 20) for lat in range(16, 150) for lng in range(1990, 2390)]
    a, b = ours(pts), dosm_lookup(pts)
    both = [(p, x, y) for p, x, y in zip(pts, a, b) if x and y]
    diff = collections.defaultdict(list)
    for p, x, y in both:
        if x[1] != y[1]:
            diff[(f'{x[0]} {x[1]}', f'{y[0]} {y[1]}')].append((round(p.y, 2), round(p.x, 2)))
    print(f'{len(both)} points in both maps; {sum(map(len, diff.values()))} with a different zone')
    for (x, y), ps in sorted(diff.items(), key=lambda kv: -len(kv[1])):
        print(f'{len(ps):4}  ours {x:38} DOSM {y:38} e.g. {ps[:2]}')
    if len(sys.argv) > 3:
        old = zones_of(sys.argv[2], sys.argv[3])(pts)
        changed = collections.Counter((o[1], x[1]) for o, x in zip(old, a) if o and x and o[1] != x[1])
        print(f'\nvs old map: {sum(changed.values())} points change zone')
        for (o, n), c in changed.most_common(30):
            print(f'{c:4}  {o} -> {n}')


if __name__ == '__main__':
    main()
