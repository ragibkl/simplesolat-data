#!/usr/bin/env python3
"""
Build Indonesia's zone map: geoBoundaries regencies (ADM2) plus the Kemenag
zones a regency map can't express.

- Island zones: Kemenag gives some remote island groups their own times
  (Pekajang in Lingga; Pulau Laut, Midai and Serasan in Natuna; Tambelan in
  Bintan), 100-300 km from their regency's main islands. Each is the
  regency's island parts within a small box around the group.
- Kota Sofifi: North Maluku's capital, inside Kota Tidore Kepulauan; a small
  circle around the town.
- Kepulauan Seribu: has no geometry in geoBoundaries; a box over the island
  chain (sea, apart from the islands), less the mainland.
- Lakes and the forest enclave (Danau Toba, Waduk Cirata, Kedungombo, the
  "Danau" lakes, "Hutan"): shapes of their own with no zone, so a point on
  them got calculated times. Each part joins the regency it borders most.

Kab. Yapen Waropen (PAP29) has no shape on purpose: it was split in 2002 into
Kepulauan Yapen and Waropen, which have their own zones.

Island centres from OpenStreetMap. Checked by tests/zone-points/ID.yaml
(python3 scripts/verify_data.py zones ID).

Usage (needs shapely):
  python3 scripts/patch_id_zones.py data/geojson/ID-adm2-geojson-20260402.json 20261102
"""

import json
import math
import os
import sys

from shapely.geometry import MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (shape name, regency, lat, lng, half-size of the box in degrees)
ISLANDS = [
    ('Pekajang', 'Lingga', -1.21, 105.27, 0.25),
    ('Pulau Laut', 'Natuna', 4.72, 107.98, 0.15),
    ('Pulau Midai', 'Natuna', 3.00, 107.78, 0.15),
    ('Pulau Serasan', 'Natuna', 2.52, 109.07, 0.20),
    ('Pulau Tambelan', 'Bintan', 0.95, 107.46, 0.40),
]
SOFIFI = ('Kota Sofifi', 'Kota Tidore Kepulauan', 0.7348, 127.5760, 5.0)  # km
# Kepulauan Seribu's islands lie in this box (Untung Jawa to Pulau Sebira).
SERIBU_BOX = (106.25, -6.02, 106.95, -5.15)
UNZONED = ['Danau', 'Danau Toba', 'Hutan', 'Waduk Cirata', 'Wadung Kedungombo']


def circle(lat, lng, km, steps=64):
    dlat = km / 111.32
    dlng = km / (111.32 * math.cos(math.radians(lat)))
    return Polygon([
        (lng + dlng * math.cos(2 * math.pi * i / steps),
         lat + dlat * math.sin(2 * math.pi * i / steps))
        for i in range(steps)
    ])


def parts(geom):
    return list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]


def main():
    base_path, date = sys.argv[1], sys.argv[2]
    base = json.load(open(base_path))
    geoms = {f['properties']['shapeName']: shape(f['geometry']).buffer(0)
             for f in base['features'] if f['geometry']}
    mainland = unary_union(list(geoms.values()))
    geoms['Kepulauan Seribu'] = box(*SERIBU_BOX).difference(mainland)
    new = []

    for name, regency, lat, lng, half in ISLANDS:
        area = box(lng - half, lat - half, lng + half, lat + half)
        group = [p for p in parts(geoms[regency]) if area.contains(p.centroid)]
        if not group:
            sys.exit(f'{name}: no {regency} island parts near {lat}, {lng}')
        geom = unary_union(group)
        geoms[regency] = geoms[regency].difference(geom)
        new.append((name, geom))

    name, regency, lat, lng, km = SOFIFI
    geom = geoms[regency].intersection(circle(lat, lng, km))
    geoms[regency] = geoms[regency].difference(geom)
    new.append((name, geom))

    # Each lake part joins the regency it shares the longest border with.
    regencies = {n: g for n, g in geoms.items() if n not in UNZONED}
    for lake in UNZONED:
        for part in parts(geoms.pop(lake)):
            edge = part.buffer(0.002)
            best = max(regencies, key=lambda n: regencies[n].intersection(edge).area)
            regencies[best] = regencies[best].union(part)
            print(f'  {lake} part at {part.centroid.y:.2f}, {part.centroid.x:.2f} -> {best}')
    geoms = regencies

    def rounded(obj):
        if isinstance(obj, float):
            return round(obj, 5)
        if isinstance(obj, (list, tuple)):
            return [rounded(x) for x in obj]
        if isinstance(obj, dict):
            return {k: rounded(v) for k, v in obj.items()}
        return obj

    features = []
    for f in base['features']:
        n = f['properties']['shapeName']
        if n in geoms:
            features.append({**f, 'geometry': mapping(geoms[n])})
    for n, g in new:
        features.append({
            'type': 'Feature',
            'properties': {'shapeName': n, 'shapeGroup': 'IDN', 'shapeType': 'ZONE'},
            'geometry': mapping(g),
        })

    out = os.path.join(ROOT, 'data', 'geojson', f'ID-adm2-geojson-{date}.json')
    with open(out, 'w') as fh:
        json.dump({**base, 'features': rounded(features)}, fh, separators=(',', ':'))
    print(f'wrote {out}: {len(features)} shapes ({len(new)} zone shapes added)')


if __name__ == '__main__':
    main()
