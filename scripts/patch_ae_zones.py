#!/usr/bin/env python3
"""
Build the UAE's zone map from the emirate map (geoBoundaries ADM1) and
Awqaf's own list of which towns use which timetable.

Awqaf publishes 60 timetables (areas) but no boundaries; the emirate map has
7 shapes, so before this every place got its emirate's main timetable (Al
Ain got Abu Dhabi's, 5-6 min off). Here each emirate is split by the
nearest listed place: a point takes the timetable of the closest town Awqaf
assigns, or of an area's main town (ANCHORS).

- sources/awqaf/places.json: Awqaf's town list (internationalprayertime
  .awqaf.gov.ae, each town with its area number), with OpenStreetMap
  coordinates kept only when inside the right emirate and near the area's
  main town.
- ANCHORS: each area's main town or site, from known coordinates.
- ISLANDS: islands and the two mountain tops (Jebel Hafeet, Jebel Jais),
  small circles carved out first.

Areas whose location Awqaf doesn't publish (oil fields, a border-guard post,
some valleys) get no shape; places there take the nearest area's timetable.
Checked by tests/zone-points/AE.yaml (python3 scripts/verify_data.py zones AE).

Usage (needs shapely):
  python3 scripts/patch_ae_zones.py data/geojson/AE-adm1-geojson-20260403.json 20261103
"""

import json
import math
import os
import sys

import shapely
from shapely.geometry import MultiPoint, MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACES = os.path.join(ROOT, 'sources', 'awqaf', 'places.json')

# zone: (lat, lng, place)
ANCHORS = {
    'AE1': (24.4539, 54.3773, 'Abu Dhabi'),
    'AE2': (24.2075, 55.7447, 'Al Ain'),
    'AE11': (23.1360, 53.7880, 'Liwa (Mezaira\'a)'),
    'AE12': (23.8367, 52.8064, 'Ghayathi'),
    'AE13': (24.0333, 51.7500, 'Al Sila'),
    'AE14': (24.1000, 53.4800, 'Al Mirfa'),
    'AE23': (24.1810, 55.0030, 'Al Khatam'),
    'AE25': (23.6520, 53.7050, 'Madinat Zayed'),
    'AE26': (24.0460, 52.6240, 'Al Hamra / Barakah'),
    'AE27': (24.1100, 52.7300, 'Al Ruwais'),
    'AE31': (24.4667, 55.3333, 'Sweihan'),
    'AE32': (25.2048, 55.2708, 'Dubai'),
    'AE33': (25.3463, 55.4209, 'Sharjah'),
    'AE34': (25.2880, 55.8820, 'Al Dhaid'),
    'AE35': (24.9700, 55.7900, 'Al Madam'),
    'AE36': (25.3390, 56.3560, 'Khor Fakkan, Kalba'),
    'AE38': (24.9320, 56.2200, 'Wadi Al Helo'),
    'AE41': (25.4052, 55.5136, 'Ajman'),
    'AE42': (24.8190, 56.0710, 'Masfout'),
    'AE43': (25.3270, 55.9930, 'Al Manama'),
    'AE44': (25.5647, 55.5552, 'Umm Al Quwain'),
    'AE45': (25.7895, 55.9432, 'Ras Al Khaimah'),
    'AE46': (26.0270, 56.0880, 'Sha\'am, Ghalilah'),
    'AE48': (25.3170, 56.1670, 'Masafi'),
    'AE52': (25.1288, 56.3265, 'Fujairah'),
    'AE53': (25.6200, 56.2700, 'Dibba'),
    'AE58': (25.1140, 56.2100, 'Wadi Saham'),
    'AE60': (24.7980, 56.1210, 'Hatta'),
}
# zone: (lat, lng, radius km, place): islands and mountain tops, small
# circles carved out first (the emirate map's coastline is too coarse for the
# islands; a summit's share of the nearest-town split would take in the towns
# below it).
ISLANDS = {
    'AE15': (24.0590, 55.7780, 2, 'Jebel Hafeet summit'),
    'AE50': (25.9436, 56.1267, 3, 'Jebel Jais'),
    'AE4': (24.4900, 52.3100, 6, 'Dalma'),
    'AE5': (24.7890, 52.5600, 3, 'Arzanah'),
    'AE6': (25.1500, 52.8750, 4, 'Das'),
    'AE7': (24.8817, 53.0717, 4, 'Zirku'),
    'AE39': (25.2320, 54.2180, 4, 'Sir Bu Nair'),
    'AE40': (25.8742, 55.0331, 4, 'Abu Musa'),
    'AE51': (26.2650, 55.3070, 4, 'Greater Tunb'),
}
# Names for areas with no anchor (their shape comes from listed towns only).
PLACE_NAMES = {
    'AE16': 'Al Wagan, Al Qua\'a',
    'AE17': 'Al Dhahra',
    'AE18': 'Al Shuwaib',
    'AE19': 'Al Khazna, Al Sad',
    'AE24': 'Al Bahia, Ghantoot',
    'AE59': 'Dubai desert (Lahbab, Al Faqa, Margham)',
}
# A listed town further than this from its area's anchor is a bad lookup.
MAX_FROM_ANCHOR_KM = 80


def km(a, b):
    return math.hypot((a[0] - b[0]) * 111.32,
                      (a[1] - b[1]) * 111.32 * math.cos(math.radians(a[0])))


def circle(lat, lng, r, steps=64):
    dlat = r / 111.32
    dlng = r / (111.32 * math.cos(math.radians(lat)))
    return Polygon([(lng + dlng * math.cos(2 * math.pi * i / steps),
                     lat + dlat * math.sin(2 * math.pi * i / steps)) for i in range(steps)])


def main():
    base_path, date = sys.argv[1], sys.argv[2]
    base = json.load(open(base_path))
    emirates = {f['properties']['shapeName']: shape(f['geometry']).buffer(0) for f in base['features']}

    seeds = [(lat, lng, zone) for zone, (lat, lng, _) in ANCHORS.items()]
    dropped = 0
    for p in json.load(open(PLACES))['places']:
        anchor = ANCHORS.get(p['zone'])
        if anchor and km((p['lat'], p['lng']), anchor[:2]) > MAX_FROM_ANCHOR_KM:
            dropped += 1
            continue
        seeds.append((p['lat'], p['lng'], p['zone']))
    print(f'{len(seeds)} seeds ({dropped} listed towns dropped: too far from their area)')

    islands = {z: circle(lat, lng, r) for z, (lat, lng, r, _) in ISLANDS.items()}
    taken = unary_union(list(islands.values()))

    # One seed per spot (towns listed twice, e.g. Dalma/Dilma, would collide).
    seeds = list({(round(lat, 4), round(lng, 4)): (lat, lng, z) for lat, lng, z in seeds}.values())
    pts = MultiPoint([(lng, lat) for lat, lng, _ in seeds])

    shapes = {}
    for name, emirate in emirates.items():
        land = emirate.difference(taken)
        # Only seeds in this emirate split it (each emirate keeps its own areas),
        # plus those within ~3 km of it: the emirate map's borders are coarse
        # (Kalba, Sharjah, falls in its Fujairah shape).
        near = emirate.buffer(0.03)
        local = [i for i, s in enumerate(seeds) if near.contains(Point(s[1], s[0]))]
        if not local:
            continue
        sub = shapely.voronoi_polygons(MultiPoint([pts.geoms[i] for i in local]),
                                       extend_to=land.envelope.buffer(1), ordered=True).geoms
        by_zone = {}
        for i, cell in zip(local, sub):
            by_zone.setdefault(seeds[i][2], []).append(cell)
        for zone, zcells in by_zone.items():
            part = land.intersection(unary_union(zcells))
            if not part.is_empty:
                shapes[zone] = shapes.get(zone, Polygon()).union(part)
    for zone, geom in islands.items():
        shapes[zone] = geom

    def rounded(obj):
        if isinstance(obj, float):
            return round(obj, 5)
        if isinstance(obj, (list, tuple)):
            return [rounded(x) for x in obj]
        if isinstance(obj, dict):
            return {k: rounded(v) for k, v in obj.items()}
        return obj

    # The shape name is shown as the place (e.g. "Al Ain, Abu Dhabi").
    names = {z: a[2] for z, a in ANCHORS.items()}
    names.update({z: a[3] for z, a in ISLANDS.items()})
    names.update(PLACE_NAMES)
    features = [{
        'type': 'Feature',
        'properties': {'shapeName': names[zone], 'shapeGroup': 'ARE', 'shapeType': 'ZONE'},
        'geometry': mapping(geom.buffer(0)),
    } for zone, geom in sorted(shapes.items(), key=lambda kv: int(kv[0][2:]))]
    out = os.path.join(ROOT, 'data', 'geojson', f'AE-adm1-geojson-{date}.json')
    with open(out, 'w') as fh:
        json.dump({**base, 'features': rounded(features)}, fh, separators=(',', ':'))
    print(f'wrote {out}: {len(features)} zone shapes')


if __name__ == '__main__':
    main()
