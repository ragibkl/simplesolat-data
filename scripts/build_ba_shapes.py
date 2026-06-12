#!/usr/bin/env python3
"""
Build data/zones/BA.yaml shape assignments from geoBoundaries BIH ADM3.

Bosnia's vaktija has 118 locations; geoBoundaries BIH ADM3 has 142 municipalities
(one of which, "Republika Srpska", is a non-municipality catch-all polygon we
drop). Mapping is keyed on shapeID, not shapeName, because two municipalities
share the name "Novi Grad" (Sarajevo's and the RS one) — the same reason Turkey
uses shapeID. Assignment:

  1. direct normalised-name match (diacritics-insensitive)
  2. explicit OVERRIDES for renamed/abbreviated names + Sarajevo sub-municipalities
  3. the two "Novi Grad" municipalities split by latitude (Sarajevo vs Bosanski Novi)
  4. nearest-centroid fallback: leftover municipalities inherit the zone of the
     geographically nearest already-anchored municipality

Municipalities absent from geoBoundaries (Višegrad, Žepa) and the Sandžak
locations (RS/ME, not in BIH geojson) get no shapes — manual selection only.

Usage: python3 scripts/build_ba_shapes.py /path/to/geoBoundaries-BIH-ADM3.geojson
"""

import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXCLUDE = {"Republika Srpska"}  # catch-all polygon, not a municipality
SANDZAK = {
    "Bijelo Polje", "Gusinje", "Nova Varoš", "Novi Pazar", "Plav", "Pljevlja",
    "Priboj", "Prijepolje", "Rožaje", "Sjenica", "Tutin",
}
OVERRIDES = {  # vaktija location -> geoBoundaries shapeName(s) (unique names only)
    "Sarajevo": ["Centar", "Stari Grad", "Novo Sarajevo", "Ilidža", "Vogošća"],
    "Bosanski Brod": ["Brod"],
    "Bosanska Gradiška": ["Gradiška"],
    "Bosanska Dubica": ["Kozarska Dubica"],
    "Bosanski Šamac": ["Šamac"],
    "Brčko": ["Brcko District"],
    "Gornji Vakuf": ["Gornji Vakuf-Uskoplje"],
    "Hlivno": ["Livno"],
    "Prozor": ["Prozor-Rama"],
    "Skender-Vakuf": ["Kneževo"],
    "Tomislav-Grad": ["Tomislavgrad"],
    "Trnovo": ["Trnovo (BiH)", "Trnovo (RS)"],
}


def norm(s):
    s = s.lower().strip()
    for a, b in {"č": "c", "ć": "c", "š": "s", "ž": "z", "đ": "dj"}.items():
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s)


def centroid(geom):
    pts = []

    def walk(c):
        if isinstance(c[0], (int, float)):
            pts.append(c)
        else:
            for x in c:
                walk(x)

    walk(geom["coordinates"])
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def main():
    geo_path = sys.argv[1]
    vak = json.load(open(os.path.join(ROOT, "sources", "vaktija", "vaktija.json"),
                        encoding="utf-8"))["locations"]
    feats = [f for f in json.load(open(geo_path, encoding="utf-8"))["features"]
             if f["properties"]["shapeName"] not in EXCLUDE]

    # municipality records keyed by unique shapeID
    munis = []  # (sid, name, centroid)
    for f in feats:
        p = f["properties"]
        munis.append((p["shapeID"], p["shapeName"], centroid(f["geometry"])))

    name_to_ids = {}
    for sid, name, _ in munis:
        name_to_ids.setdefault(name, []).append(sid)
    override_names = {s for v in OVERRIDES.values() for s in v}

    vak_norm = {norm(v): v for v in vak}
    assign = {}  # shapeID -> (zone, method)

    # 1. direct name match (skip duplicates and override-managed names)
    for sid, name, _ in munis:
        if name == "Novi Grad" or name in override_names:
            continue
        z = vak_norm.get(norm(name))
        if z:
            assign[sid] = (z, "name")

    # 2. overrides (names here are all unique)
    for vloc, names in OVERRIDES.items():
        for nm in names:
            for sid in name_to_ids.get(nm, []):
                assign[sid] = (vloc, "override")

    # 3. split the two "Novi Grad" by latitude
    for sid, name, c in munis:
        if name == "Novi Grad":
            assign[sid] = ("Sarajevo" if c[1] < 44.5 else "Bosanski Novi", "override")

    # 4. nearest-centroid for the rest
    cent = {sid: c for sid, _, c in munis}
    anchors = [(sid, cent[sid]) for sid in assign]
    for sid, name, c in munis:
        if sid in assign:
            continue
        bsid, bc = min(anchors, key=lambda a: (a[1][0]-c[0])**2 + (a[1][1]-c[1])**2)
        assign[sid] = (assign[bsid][0], f"nearest:{name_of(munis, bsid)}")

    name_by_id = {sid: name for sid, name, _ in munis}
    zone_shapes = {}  # zone -> [(sid, name)]
    for sid, (zone, _) in assign.items():
        zone_shapes.setdefault(zone, []).append((sid, name_by_id[sid]))

    write_zones(vak, zone_shapes)
    report(munis, assign, zone_shapes, vak)


def name_of(munis, sid):
    for s, name, _ in munis:
        if s == sid:
            return name
    return sid


def write_zones(vak, zone_shapes):
    lines = [
        "# Bosnia (Islamic Community in BiH — Vaktija) zones.",
        "# Locations from sources/vaktija/vaktija.json; shapes (shapeID, like TR) from",
        "# geoBoundaries BIH ADM3 via scripts/build_ba_shapes.py. Sandžak (state: Sandžak)",
        "# is in RS/ME — no BIH geojson, manual selection only. Višegrad & Žepa are absent",
        "# from geoBoundaries (manual only).",
        "zones:",
    ]
    for loc_id, name in enumerate(vak):
        state = "Sandžak" if name in SANDZAK else "Bosna i Hercegovina"
        shapes = sorted(zone_shapes.get(name, []), key=lambda x: x[1])
        lines += [
            f"  - code: BA{loc_id}",
            f"    country: BA",
            f"    state: {state}",
            f"    location: {name}",
            f"    timezone: Europe/Sarajevo",
        ]
        if shapes:
            lines.append("    shapes:")
            lines += [f"      - {sid}  # {nm}" for sid, nm in shapes]
        else:
            lines.append("    shapes: []")
        lines.append("")
    with open(os.path.join(ROOT, "data", "zones", "BA.yaml"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def report(munis, assign, zone_shapes, vak):
    by_method = {}
    for _, (_, m) in assign.items():
        by_method[m.split(":")[0]] = by_method.get(m.split(":")[0], 0) + 1
    print(f"Municipalities assigned: {len(assign)}/{len(munis)}  by method: {by_method}")
    print(f"vaktija zones with shapes: {len(zone_shapes)}/{len(vak)}")
    print("\nNEAREST-CENTROID assignments (review):")
    for sid, (zone, m) in sorted(assign.items(), key=lambda x: x[1][0]):
        if m.startswith("nearest"):
            print(f"   {name_of(munis, sid):26} -> {zone:18} ({m})")
    no_shape = [v for v in vak if v not in zone_shapes and v not in SANDZAK]
    print(f"\nBiH zones with NO shape (manual-only GPS gap): {no_shape}")
    print(f"Sandžak zones (manual-only, expected): {sum(1 for v in vak if v in SANDZAK)}")


if __name__ == "__main__":
    main()
