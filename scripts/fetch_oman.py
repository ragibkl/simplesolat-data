#!/usr/bin/env python3
"""
Generate Oman's prayer times with the method of the Ministry of Endowments
and Religious Affairs (MERA).

MERA publishes no timetable; its official app ("تقويم عُمان",
om.gov.mara.omanical) computes the times on the phone for 101 official cities
(sources/mara/cities.json, from the app's assets/mcal59.sqlite). This is a
line-by-line port of the app's calculation (co.smart_app.Hijri_Cal_Tools),
rounding included, so our times are the app's: fajr and isha at 18 degrees,
sunrise/sunset at -0.833 degrees, Shafi'i asr, UTC+4, and 5 minutes added to
dhuhr, asr and maghrib. Like Bosnia's vaktija, it's the authority's own
method, run here and published as tables.

The app shows no imsak or duha: imsak = fajr (as for Saudi Arabia and Qatar),
no dhuha.

Usage:
  python3 scripts/fetch_oman.py [year ...]   # this year and next by default
  python3 scripts/fetch_oman.py --zones      # (re)generate data/zones/OM.yaml
"""

import calendar
import json
import math
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CITIES = os.path.join(ROOT, "sources", "mara", "cities.json")
PI = 3.141592653589793


def cities():
    return json.load(open(CITIES, encoding="utf-8"))["cities"]


# Five entries in the app's table have decimal degrees typed into the minutes
# columns (Nakhal "23 40, 57 82" is 23.40N 57.82E). The app reads them as
# minutes, which moves the towns up to 60 km and gives times 1-4 min early;
# we use the real positions (the method is the ministry's, the typo isn't).
DECIMAL_TYPOS = {87, 92, 98, 99, 100}  # Nakhal, Wadi Al Maawil, Khazzan, Wadi Alhaitham, Haifudh

# Cities at the same point as another (same times): they share its shape.
SAME_PLACE = {49: 18}  # Seeq (Saiq) -> Aljabel Alakhdhar


def display_name(c):
    n = c["name_en"].strip()
    return n[0].upper() + n[1:]


def coords(c):
    """(lat, lng) in degrees, as the app computes them (degrees + minutes / 60),
    except the DECIMAL_TYPOS."""
    div = 100.0 if c["id"] in DECIMAL_TYPOS else 60.0
    return c["lat_deg"] + c["lat_min"] / div, c["lon_deg"] + c["lon_min"] / div


def shape_name(c, all_cities):
    """The map shape's name: the city, with any city at the same point."""
    others = [display_name(x) for x in all_cities if SAME_PLACE.get(x["id"]) == c["id"]]
    return display_name(c) + (f" ({', '.join(others)})" if others else "")


def jint(x):
    # Java's (int) cast: truncate toward zero.
    return float(int(x))


def times(n4, e4, y, m, d):
    """The app's Hijri_Cal_Tools.calculation for latitude n4 and longitude e4,
    returning hours for fajr, sunrise, dhuhr, asr, maghrib, isha."""
    rad = lambda x: x * PI / 180.0
    deg = lambda x: x * 180.0 / PI
    v1 = ((367.0 * y - jint((y + jint((m + 9.0) / 12.0)) * 1.75)) + jint((m / 9.0) * 275.0) + d) - 730531.5
    v2 = (0.9856474 * v1 + 280.461) % 360.0
    v3 = (v1 * 0.9856003 + 357.528) % 360.0
    v4 = v2 + math.sin(rad(v3)) * 1.915 + math.sin(rad(v3 * 2.0)) * 0.02
    v5 = 23.439 - v1 * 4.0e-7
    v6 = deg(math.atan(math.cos(rad(v5)) * math.tan(rad(v4))))
    v7 = v6 - math.floor(v6 / 360.0) * 360.0
    valpha = v7 + (math.floor(v4 / 90.0) - math.floor(v7 / 90.0)) * 90.0
    v8 = (v1 * 0.985647352 + 100.46) - math.floor((v1 * 0.985647352 + 100.46) / 360.0) * 360.0
    v9 = deg(math.asin(math.sin(rad(v5)) * math.sin(rad(v4))))
    v10 = (valpha - v8) - math.floor((valpha - v8) / 360.0) * 360.0
    v12 = (v10 - e4) / 15.0 + 4.0
    s9, c9 = math.sin(rad(v9)), math.cos(rad(v9))
    s4, c4 = math.sin(rad(n4)), math.cos(rad(n4))
    v14 = deg(math.asin(s4 * s9 + c4 * c9))
    v15 = 90.0 - deg(math.atan(1.0 / (1.0 / math.tan(rad(v14)) + 1.0)))
    v16 = deg(math.acos((math.sin(rad(90.0 - v15)) - s9 * s4) / (c9 * c4))) / 15.0
    v22 = deg(math.acos((math.sin(-0.01454441043328608) - s9 * s4) / (c9 * c4)))
    v23 = v12 - v22 / 15.0
    v25 = v12 + v22 / 15.0
    v27 = deg(math.acos((math.sin(-0.3141592653589793) - s9 * s4) / (c9 * c4)))
    v28 = v12 + v27 / 15.0
    v31 = v12 - v27 / 15.0
    five = 0.08333333333333333
    dhuhr = v12 + five
    return v31, v23, dhuhr, dhuhr + v16, v25 + five, v28


def hhmm(h):
    """The app's getTimeHHMMCal: 30 seconds or more rounds the minute up."""
    i = int(h)
    m2 = (h - i) * 60.0
    mi = int(m2)
    if int((m2 - mi) * 60.0) >= 30:
        mi += 1
    if mi == 60:
        i += 1
        mi = 0
    return f"{i:02d}:{mi:02d}"


def month_rows(c, y, m):
    rows = []
    for d in range(1, calendar.monthrange(y, m)[1] + 1):
        f, sr, dh, a, mg, i = (hhmm(t) for t in times(*coords(c), y, m, d))
        rows.append({"date": f"{y}-{m:02d}-{d:02d}", "imsak": f, "fajr": f, "syuruk": sr,
                     "dhuhr": dh, "asr": a, "maghrib": mg, "isha": i})
    return rows


def generate(years):
    written = 0
    for c in cities():
        out_dir = os.path.join(ROOT, "data", "prayer-times", "OM", f"OM{c['id']}")
        os.makedirs(out_dir, exist_ok=True)
        for y in years:
            for m in range(1, 13):
                with open(os.path.join(out_dir, f"{y}-{m:02d}.json"), "w", encoding="utf-8") as f:
                    json.dump(month_rows(c, y, m), f, indent=2)
                    f.write("\n")
                written += 1
    print(f"Done: {written} files written")


def emit_zones():
    lines = [
        "# Oman (Ministry of Endowments and Religious Affairs): the 101 cities of the",
        "# ministry's official app. Generated by scripts/fetch_oman.py --zones;",
        "# shapes from scripts/patch_om_zones.py (each city's nearest-city area).",
        "zones:",
    ]
    all_cities = cities()
    for c in all_cities:
        lines += [
            f"  - code: OM{c['id']}",
            "    country: OM",
            "    state: Oman",
            f"    location: {display_name(c)}",
            "    timezone: Asia/Muscat",
        ]
        if c["id"] in SAME_PLACE:
            lines += ["    shapes: []  # same point as OM%d" % SAME_PLACE[c["id"]], ""]
        else:
            lines += ["    shapes:", f"      - {shape_name(c, all_cities)}", ""]
    out = os.path.join(ROOT, "data", "zones", "OM.yaml")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {out}")


def main():
    if "--zones" in sys.argv[1:]:
        emit_zones()
        return
    now = datetime.now()
    generate([int(a) for a in sys.argv[1:]] or [now.year, now.year + 1])


if __name__ == "__main__":
    main()
