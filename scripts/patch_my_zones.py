#!/usr/bin/env python3
"""
Build Malaysia's zone map: geoBoundaries districts (ADM2) plus the JAKIM zones
a district map can't express, carved out as their own shapes.

A district maps to one zone, but some JAKIM zones are smaller than a district
or cut across one:
- Zon Khas: hilltops and special areas JAKIM defines by a reference point
  and altitude (Gunung Jerai, Bukit Larut, Gunung Kinabalu, Genting Sempah,
  Janda Baik, Bukit Tinggi, Genting Highlands, Bukit Fraser, Kampung
  Patarikan). Small circles around the reference points, kept small so
  nearby lowland towns (Gurun, Taiping, Kundasang...) keep their own zone.
- Mukim zones: Belum and Temengor (PRK04); Rompin district split by mukim
  (PHG07 = Mukim Rompin, Endau, Pontian; Keratong and Muadzam Shah stay
  PHG02); Putrajaya (WLY01), which the district map folds into Sepang.
- Islands: Pulau Tioman (PHG01) from Rompin, Pulau Aur and Pemanggil (JHR01)
  from Mersing.

Each new shape is cut out of the districts it overlaps (so every point is in
exactly one shape) and named here; data/zones/MY.yaml maps the names to
zones, and tests/zone-points/MY.yaml checks the result
(python3 scripts/verify_data.py zones MY).

Thanks to Afiq Hazwan (MySolat) for finding these and sharing his test
points and the Rompin traps.

Sources: JAKIM reference points from e-solat "Lampiran B" (Titik Rujukan
Hitungan Waktu Solat); mukims from geoBoundaries MYS ADM3 (CC BY 4.0), the
needed ones copied to sources/geoboundaries/MYS-ADM3-selected.geojson.

Usage (needs shapely):
  python3 scripts/patch_my_zones.py data/geojson/MY-adm2-geojson-20260402.json 20261101
"""

import json
import math
import os
import sys

from shapely.geometry import MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUKIMS = os.path.join(ROOT, 'sources', 'geoboundaries', 'MYS-ADM3-selected.geojson')

# Zon Khas: (shape name, lat, lng, radius km). Reference points from JAKIM
# where given; extra points where JAKIM's zone names several places.
CIRCLES = [
    ('Zon Khas Gunung Jerai', 5.7875, 100.4417, 2.5),      # JAKIM, 1,214 m
    ('Zon Khas Bukit Larut', 4.8667, 100.8000, 2.5),       # JAKIM, 945 m
    ('Zon Khas Gunung Kinabalu', 6.0833, 116.5333, 4.0),   # JAKIM
    ('Zon Khas Bukit Tinggi', 3.3833, 101.8250, 2.5),      # JAKIM 686 m and Afiq's point
    ('Zon Khas Genting Sempah', 3.3167, 101.7833, 2.0),
    ('Zon Khas Janda Baik', 3.3200, 101.8500, 2.5),
    ('Zon Khas Genting Highlands', 3.4239, 101.7933, 2.5),
    ('Zon Khas Bukit Fraser', 3.7167, 101.7500, 2.5),
    # Between JAKIM's reference point and Afiq's (Merapok), 6.5 km apart.
    ('Zon Khas Kampung Patarikan', 4.9406, 115.5080, 3.5),
]


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
    districts = {f['properties']['shapeName']: shape(f['geometry']) for f in base['features']}
    mukims = {}
    for f in json.load(open(MUKIMS))['features']:
        mukims[f['properties']['shapeName']] = shape(f['geometry'])

    def mukim_in(district, *names):
        # Same-named mukims exist in other states: keep only the part inside
        # this district.
        return unary_union([mukims[n] for n in names]).intersection(districts[district])

    new = []  # (name, geometry), in priority order: earlier wins overlaps

    for name, lat, lng, km in CIRCLES:
        new.append((name, circle(lat, lng, km)))

    # Islands, from the districts' own shapes (keeps their coastline).
    rompin_parts = parts(districts['Rompin'])
    tioman = [p for p in rompin_parts if p.centroid.x > 104.0]
    new.append(('Pulau Tioman', unary_union(tioman)))
    aur_box = mukims['MUKIM PULAU AUR'].buffer(0.05)
    aur = [p for p in parts(districts['Mersing']) if aur_box.contains(p.centroid)]
    new.append(('Pulau Aur dan Pulau Pemanggil', unary_union(aur)))

    # Rompin: Mukim Rompin, Endau and Pontian (with their towns) are PHG07;
    # Keratong and the Muadzam Shah towns stay PHG02. Cut from the district so
    # the coastline is the district's own, but kept within about 500 m of the
    # PHG07 mukims: the district and mukim maps disagree near the borders, and
    # the slivers must not become PHG07. (Mukims and towns are separate units
    # in geoBoundaries, so towns are listed too, else they'd be holes.)
    mainland = unary_union([p for p in rompin_parts if p.centroid.x <= 104.0])
    phg07 = mukim_in(
        'Rompin', 'MUKIM ROMPIN', 'MUKIM ENDAU', 'MUKIM PONTIAN', 'BANDAR ROMPIN I',
        'BANDAR ROMPIN II', 'BANDAR ROMPIN III', 'BANDAR ROMPIN IV', 'PEKAN KUALA ROMPIN',
        'BANDAR BAHARU ROMPIN', 'PEKAN ROMPIN', 'BANDAR ENDAU', 'BANDAR PONTIAN')
    keratong = mukim_in('Rompin', 'MUKIM KERATONG', 'BANDAR MUADZAM SHAH I', 'BANDAR MUADZAM SHAH II')
    new.append(('Rompin (Zon Khas)', mainland.intersection(phg07.buffer(0.005)).difference(keratong)))

    new.append(('Belum dan Temengor', mukim_in('Hulu Perak', 'MUKIM BELUM', 'MUKIM TEMENGOR')))
    new.append(('Putrajaya', mukims['BANDAR PUTRAJAYA']))

    # Make the new shapes disjoint (earlier wins), then cut them out of the
    # districts.
    taken = None
    clean = []
    for name, geom in new:
        geom = geom.buffer(0)
        if taken is not None:
            geom = geom.difference(taken)
        clean.append((name, geom))
        taken = geom if taken is None else taken.union(geom)

    features = []
    for f in base['features']:
        geom = shape(f['geometry']).difference(taken)
        if geom.is_empty:
            continue
        features.append({**f, 'geometry': mapping(geom)})
    for name, geom in clean:
        features.append({
            'type': 'Feature',
            'properties': {'shapeName': name, 'shapeGroup': 'MYS', 'shapeType': 'ZONE'},
            'geometry': mapping(geom),
        })

    def rounded(obj):
        if isinstance(obj, float):
            return round(obj, 5)
        if isinstance(obj, (list, tuple)):
            return [rounded(x) for x in obj]
        if isinstance(obj, dict):
            return {k: rounded(v) for k, v in obj.items()}
        return obj

    out = os.path.join(ROOT, 'data', 'geojson', f'MY-adm2-geojson-{date}.json')
    with open(out, 'w') as fh:
        json.dump({**base, 'features': rounded(features)}, fh, separators=(',', ':'))
    print(f'wrote {out}: {len(features)} shapes ({len(clean)} zone shapes added)')


if __name__ == '__main__':
    main()
