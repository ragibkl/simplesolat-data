#!/usr/bin/env python3
"""
Fetch Qatar's prayer times from the Ministry of Awqaf and Islamic Affairs
(islam.gov.qa). One national timetable; the API returns one day per call, for
any date.

The ministry publishes fajr, sunrise, dhuhr, asr, maghrib and isha. There's
no separate imsak, so imsak = fajr (as for the UAE and Saudi Arabia).

Writes data/prayer-times/QA/QA01/{year}-{month}.json for this year and next
(months already complete are skipped).

Usage: python3 scripts/fetch_qatar.py [year ...]
"""

import calendar
import json
import os
import sys
import time
from datetime import datetime
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import month_complete  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://meiaservicesext.islam.gov.qa/ServicesBrokerGatewayAPI/api/PrayerTimes?date={d:02d}-{m:02d}-{y}"
ZONE = "QA01"
# Fridays list Jummah in place of Dhuhr.
NAMES = {"Fajr": "fajr", "Sunrise": "syuruk", "Dhuhr": "dhuhr", "Jummah": "dhuhr", "Asr": "asr",
         "Maghrib": "maghrib", "Isha": "isha"}


def fetch_day(y, m, d):
    for attempt in range(4):
        try:
            req = Request(API.format(y=y, m=m, d=d), headers={"User-Agent": "simplesolat-data"})
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            break
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    g = data["gregorianDate"]
    if (g["year"], g["month"], g["day"]) != (y, m, d):
        raise RuntimeError(f"asked for {y}-{m}-{d}, got {g['date']}")
    times = {NAMES[t["prayerTimeName"]]: f"{t['time']['hour']:02d}:{t['time']['minutes']:02d}"
             for t in data["times"] if t["prayerTimeName"] in NAMES}
    return {"date": f"{y}-{m:02d}-{d:02d}", "imsak": times["fajr"],
            "fajr": times["fajr"], "syuruk": times["syuruk"], "dhuhr": times["dhuhr"],
            "asr": times["asr"], "maghrib": times["maghrib"], "isha": times["isha"]}


def main():
    now = datetime.now()
    years = [int(a) for a in sys.argv[1:]] or [now.year, now.year + 1]
    out_dir = os.path.join(ROOT, "data", "prayer-times", "QA", ZONE)
    written = skipped = 0
    for y in years:
        for m in range(1, 13):
            path = os.path.join(out_dir, f"{y}-{m:02d}.json")
            if month_complete(path, str(y), f"{m:02d}"):
                skipped += 1
                continue
            rows = []
            for d in range(1, calendar.monthrange(y, m)[1] + 1):
                rows.append(fetch_day(y, m, d))
                time.sleep(0.2)
            os.makedirs(out_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rows, f, indent=2)
                f.write("\n")
            written += 1
            print(f"wrote {path}")
    print(f"Done: {written} written, {skipped} skipped")


if __name__ == "__main__":
    main()
