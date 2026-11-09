#!/usr/bin/env python3
"""
Fetch Malaysia's district (daerah) boundaries from OpenStreetMap, as the base
map for scripts/build_my_map.sh.

OSM has the districts as admin_level 6 relations inside each state (admin
level 4). The three federal territories (Kuala Lumpur, Labuan, Putrajaya)
have no districts, and Perlis is a single district in OSM, so the territory
or state itself is used. Each relation's outer and
inner ways are assembled into (multi)polygons with shapely.

Output: one GeoJSON feature per district with properties
  shapeName  district name (English name where OSM has one, " District" dropped)
  state      the state's ISO 3166-2 code (MY-01 ... MY-16)
  osm_id     the relation id
Unsimplified; build_my_map.sh simplifies it with shared borders (mapshaper).

Data © OpenStreetMap contributors, ODbL 1.0
(https://www.openstreetmap.org/copyright).

Usage (needs shapely):
  python3 scripts/fetch_osm_my_districts.py /tmp/MY-osm-districts.geojson
"""

import json
import sys
import time
import urllib.parse
import urllib.request

from shapely.geometry import LineString, mapping
from shapely.ops import polygonize, unary_union

OVERPASS = 'https://overpass-api.de/api/interpreter'
UA = 'simplesolat-data (https://github.com/ragibkl/simplesolat-data)'
TERRITORIES = {'MY-14', 'MY-15', 'MY-16'}


def overpass(query):
    req = urllib.request.Request(
        OVERPASS, data=urllib.parse.urlencode({'data': query}).encode(),
        headers={'User-Agent': UA})
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(req, timeout=300))
        except Exception as e:  # rate limits, timeouts: wait and retry
            print(f'  retry ({e})', file=sys.stderr)
            time.sleep(30 * (attempt + 1))
    raise SystemExit('overpass failed')


def polygons(rel):
    def rings(role):
        lines = [LineString([(p['lon'], p['lat']) for p in m['geometry']])
                 for m in rel['members']
                 if m['type'] == 'way' and m.get('role') == role and m.get('geometry')]
        return list(polygonize(unary_union(lines))) if lines else []
    geom = unary_union(rings('outer'))
    inner = rings('inner')
    if inner:
        geom = geom.difference(unary_union(inner))
    return geom


def name(tags):
    n = tags.get('name:en') or tags['name']
    return n[:-len(' District')] if n.endswith(' District') else n


def main():
    out_path = sys.argv[1]
    states = overpass('[out:json][timeout:120];area["ISO3166-1"="MY"][admin_level=2]->.m;'
                      'rel(area.m)[boundary=administrative][admin_level=4]["ISO3166-2"];out tags;')
    features = []
    for st in sorted(states['elements'], key=lambda e: e['tags']['ISO3166-2']):
        code = st['tags']['ISO3166-2']
        level = 4 if code in TERRITORIES else 6
        query = (f'[out:json][timeout:280];rel({st["id"]});map_to_area->.s;'
                 f'rel(area.s)[boundary=administrative][admin_level={level}];out geom;')
        if level == 4:
            query = f'[out:json][timeout:280];rel({st["id"]});out geom;'
        rels = overpass(query)['elements']
        if not rels:  # one-district state (Perlis): the state itself
            rels = overpass(f'[out:json][timeout:280];rel({st["id"]});out geom;')['elements']
        for rel in rels:
            geom = polygons(rel)
            if geom.is_empty:
                print(f'  {code} {name(rel["tags"])}: no geometry, skipped', file=sys.stderr)
                continue
            features.append({'type': 'Feature',
                             'properties': {'shapeName': name(rel['tags']), 'state': code,
                                            'osm_id': rel['id']},
                             'geometry': mapping(geom)})
        print(f'{code} {name(st["tags"])}: {len(rels)}', file=sys.stderr)
        time.sleep(5)
    with open(out_path, 'w') as fh:
        json.dump({'type': 'FeatureCollection', 'features': features}, fh)
    print(f'wrote {out_path}: {len(features)} districts', file=sys.stderr)


if __name__ == '__main__':
    main()
