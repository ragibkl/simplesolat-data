#!/usr/bin/env python3
"""
Build data/zones/AL.yaml shape assignments from geoBoundaries ALB ADM2.

Albania's Diyanet set has 20 cities (sources/diyanet/locations-al.yaml);
geoBoundaries ALB ADM2 has the ~36 old rrethe (districts). Mapping is keyed on
shapeID because geoBoundaries duplicates two names (Vlorë, Kuçovë). Assignment:

  1. direct normalised-name match (Tiranë, Durrës, Berat, ...)
  2. SEAT overrides: a city that is the seat of a differently-named district
     (Bajram Curri -> Tropojë, Rrëshen -> Mirditë, Ersekë -> Kolonjë,
      Peshkopi -> Dibër, Burrel -> Mat)
  3. Korçë fix: geoBoundaries mislabels Korçë's polygon as a 2nd "Kuçovë"
     (centroid ~20.7E/40.7N) — assigned to Korçë by shapeID
  4. nearest-centroid fallback for the remaining rrethe

Usage: python3 scripts/build_al_shapes.py /path/to/geoBoundaries-ALB-ADM2.geojson
"""

import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# city display name -> geoBoundaries ADM2 shapeName(s) (city is the district seat)
SEAT_OVERRIDES = {
    "Bajram Curri": ["Tropojë"],
    "Rrëshen": ["Mirditë"],
    "Ersekë": ["Kolonjë"],
    "Peshkopi": ["Dibër"],
    "Burrel": ["Mat"],
}


def norm(s):
    s = s.lower().strip()
    for a, b in {"ë": "e", "ç": "c"}.items():
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


def load_cities():
    """Read (zone_code, display_name) from sources/diyanet/locations-al.yaml."""
    path = os.path.join(ROOT, "sources", "diyanet", "locations-al.yaml")
    cities, cur = [], {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r'\s+- id:\s+"?(\d+)"?', line)
            if m:
                if cur:
                    cities.append(cur)
                cur = {"id": m.group(1)}
                continue
            m = re.match(r'\s+(\w+):\s+"?(.+?)"?\s*$', line)
            if m and cur:
                cur[m.group(1)] = m.group(2)
        if cur:
            cities.append(cur)
    return [(f"AL{c['id']}", c["district"]) for c in cities]


def main():
    feats = json.load(open(sys.argv[1], encoding="utf-8"))["features"]
    munis = [(f["properties"]["shapeID"], f["properties"]["shapeName"], centroid(f["geometry"]))
             for f in feats]
    cities = load_cities()                       # [(AL11203, "Tiranë"), ...]
    name_to_zone = {norm(n): z for z, n in cities}
    seat_names = {s for v in SEAT_OVERRIDES.values() for s in v}

    assign = {}  # shapeID -> (zone, method)

    # 1. direct name match (skip seat-managed names)
    for sid, name, _ in munis:
        if name in seat_names:
            continue
        z = name_to_zone.get(norm(name))
        if z:
            assign[sid] = (z, "name")

    # 2. seat overrides
    disp_to_zone = {n: z for z, n in cities}
    for city, shapes in SEAT_OVERRIDES.items():
        for sid, name, _ in munis:
            if name in shapes:
                assign[sid] = (disp_to_zone[city], "seat")

    # 3. Korçë fix — the eastern (lon > 20.4) "Kuçovë" polygon is really Korçë
    korce_zone = disp_to_zone["Korçë"]
    for sid, name, c in munis:
        if name == "Kuçovë" and c[0] > 20.4:
            assign[sid] = (korce_zone, "korce-fix")

    # 4. nearest-centroid for the rest
    cent = {sid: c for sid, _, c in munis}
    name_by_id = {sid: n for sid, n, _ in munis}
    anchors = [(sid, cent[sid]) for sid in assign]
    for sid, name, c in munis:
        if sid in assign:
            continue
        bsid, _ = min(anchors, key=lambda a: (a[1][0]-c[0])**2 + (a[1][1]-c[1])**2)
        assign[sid] = (assign[bsid][0], f"nearest:{name_by_id[bsid]}")

    zone_shapes = {}
    for sid, (zone, _) in assign.items():
        zone_shapes.setdefault(zone, []).append((sid, name_by_id[sid]))

    # ---- write AL.yaml ----
    lines = [
        "# Albania (Diyanet — published by the Islamic Community of Albania, KMSH) zones.",
        "# Cities from sources/diyanet/locations-al.yaml; shapes (shapeID) from geoBoundaries",
        "# ALB ADM2 via scripts/build_al_shapes.py.",
        "zones:",
    ]
    for zone, name in cities:
        shapes = sorted(zone_shapes.get(zone, []), key=lambda x: x[1])
        lines += [
            f"  - code: {zone}",
            f"    country: AL",
            f"    state: Albania",
            f"    location: {name}",
            f"    timezone: Europe/Tirane",
        ]
        if shapes:
            lines.append("    shapes:")
            lines += [f"      - {sid}  # {nm}" for sid, nm in shapes]
        else:
            lines.append("    shapes: []")
        lines.append("")
    with open(os.path.join(ROOT, "data", "zones", "AL.yaml"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # ---- report ----
    by_method = {}
    for _, (_, m) in assign.items():
        by_method[m.split(":")[0]] = by_method.get(m.split(":")[0], 0) + 1
    print(f"ADM2 polygons assigned: {len(assign)}/{len(munis)}  by method: {by_method}")
    print(f"cities with shapes: {len(zone_shapes)}/{len(cities)}")
    print("\nNEAREST-CENTROID assignments (review):")
    for sid, (zone, m) in sorted(assign.items(), key=lambda x: x[1][0]):
        if m.startswith("nearest"):
            print(f"   {name_by_id[sid]:16} -> {disp_name(cities, zone):14} ({m})")
    no = [n for z, n in cities if z not in zone_shapes]
    print(f"\ncities with NO shape (manual-only): {no}")


def disp_name(cities, zone):
    for z, n in cities:
        if z == zone:
            return n
    return zone


if __name__ == "__main__":
    main()
