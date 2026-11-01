#!/usr/bin/env python3
"""
Build the Serbia and Montenegro maps: only the Sandžak municipalities that
the Islamic Community in BiH's vaktija covers (scripts/fetch_vaktija.py
SANDZAK_COUNTRY). Anywhere else in those countries finds no shape, so it gets
calculated times. Shapes are named after the town (shown as the place).

Sources: geoBoundaries SRB ADM2 and MNE ADM1 (ODbL 1.0).

Usage:
  python3 scripts/build_sandzak_shapes.py geoBoundaries-SRB-ADM2.geojson geoBoundaries-MNE-ADM1.geojson 20261103
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# geoBoundaries name -> vaktija town
TOWNS = {
    'RS': {'Nova Varos Municipality': 'Nova Varoš', 'Novi Pazar City': 'Novi Pazar',
           'Priboj Municipality': 'Priboj', 'Prijepolje Municipality': 'Prijepolje',
           'Sjenica Municipality': 'Sjenica', 'Tutin Municipality': 'Tutin'},
    'ME': {'Bijelo Polje Municipality': 'Bijelo Polje', 'Gusinje Municipality': 'Gusinje',
           'Plav Municipality': 'Plav', 'Pljevlja Municipality': 'Pljevlja',
           'Rožaje Municipality': 'Rožaje'},
}


def rounded(obj):
    if isinstance(obj, float):
        return round(obj, 5)
    if isinstance(obj, list):
        return [rounded(x) for x in obj]
    if isinstance(obj, dict):
        return {k: rounded(v) for k, v in obj.items()}
    return obj


def main():
    srb, mne, date = sys.argv[1], sys.argv[2], sys.argv[3]
    for cc, path, level in (('RS', srb, 'adm2'), ('ME', mne, 'adm1')):
        base = json.load(open(path, encoding='utf-8'))
        features = []
        for f in base['features']:
            town = TOWNS[cc].get(f['properties']['shapeName'])
            if town:
                features.append({**f, 'properties': {**f['properties'], 'shapeName': town},
                                 'geometry': rounded(f['geometry'])})
        missing = set(TOWNS[cc].values()) - {f['properties']['shapeName'] for f in features}
        if missing:
            sys.exit(f'{cc}: not found in {path}: {sorted(missing)}')
        out = os.path.join(ROOT, 'data', 'geojson', f'{cc}-{level}-geojson-{date}.json')
        with open(out, 'w', encoding='utf-8') as fh:
            json.dump({**base, 'features': features}, fh, ensure_ascii=False, separators=(',', ':'))
        print(f'wrote {out}: {len(features)} shapes')


if __name__ == '__main__':
    main()
