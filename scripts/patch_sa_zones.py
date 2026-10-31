#!/usr/bin/env python3
"""
Build Saudi Arabia's zone map: the country split by nearest official city.

KACST publishes times for 173 official cities and governorates
(sources/ummulqura/cities.json), computed for each city's point, so a place
takes the times of the nearest one: each city's shape is its nearest-city
area (a Voronoi cell) within the country. Shapes are named after the city
(shown as the place).

Source: geoBoundaries SAU ADM0 (ODbL 1.0), simplified to ~100 m.

Usage (needs shapely):
  python3 scripts/patch_sa_zones.py geoBoundaries-SAU-ADM0.geojson 20261103
"""

import json
import os
import sys

import shapely
from shapely.geometry import MultiPoint, mapping, shape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CITIES = os.path.join(ROOT, 'sources', 'ummulqura', 'cities.json')


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
    country = shape(base['features'][0]['geometry']).buffer(0).simplify(0.001, preserve_topology=True)
    cities = json.load(open(CITIES, encoding='utf-8'))
    points = MultiPoint([(c['longitude'], c['latitude']) for c in cities])
    cells = shapely.voronoi_polygons(points, extend_to=country.envelope.buffer(1), ordered=True).geoms
    features = []
    for city, cell in zip(cities, cells):
        part = country.intersection(cell)
        if part.is_empty:
            sys.exit(f"{city['name_en']}: its area is outside the country")
        features.append({
            'type': 'Feature',
            'properties': {'shapeName': city['name_en'], 'shapeGroup': 'SAU', 'shapeType': 'ZONE'},
            'geometry': rounded(mapping(part)),
        })
    out = os.path.join(ROOT, 'data', 'geojson', f'SA-adm0-geojson-{date}.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump({**{k: v for k, v in base.items() if k != 'features'}, 'features': features},
                  fh, ensure_ascii=False, separators=(',', ':'))
    print(f'wrote {out}: {len(features)} shapes')


if __name__ == '__main__':
    main()
