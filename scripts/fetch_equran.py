#!/usr/bin/env python3
"""
Fetch EQuran.id (Indonesia) prayer times.

Per zone per month, parallel fetching (10 workers).
Writes to data/prayer-times/ID/{zone}/{year}-{month}.json.
Reads zone list from data/zones/ID.yaml.

Usage: python3 scripts/fetch_equran.py [year]
  Default: current year and next year
"""

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_URL = "https://equran.id/api/v2/shalat"


def parse_zones():
    """Read ID zones from data/zones/ID.yaml. Returns list of {code, state, location}."""
    zones = []
    zones_path = os.path.join(ROOT, "data", "zones", "ID.yaml")
    current = {}
    with open(zones_path) as f:
        for line in f:
            m = re.match(r'\s+- code:\s+(\S+)', line)
            if m:
                if current:
                    zones.append(current)
                current = {'code': m.group(1)}
                continue
            m = re.match(r'\s+state:\s+(.+)', line)
            if m:
                current['state'] = m.group(1).strip()
                continue
            m = re.match(r'\s+location:\s+(.+)', line)
            if m:
                current['location'] = m.group(1).strip()
                continue
    if current:
        zones.append(current)
    return zones


def fetch_month(provinsi, kabkota, bulan, tahun):
    """Fetch one month of prayer times. Returns list of records or None on 404/error."""
    body = json.dumps({
        "provinsi": provinsi,
        "kabkota": kabkota,
        "bulan": bulan,
        "tahun": tahun,
    }).encode()

    req = Request(API_URL, data=body, headers={
        "User-Agent": "Simplesolat/1.0",
        "Content-Type": "application/json",
    })

    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except HTTPError:
        return None
    except Exception:
        return None

    if data.get("code") != 200:
        return None

    return data["data"]["jadwal"]


def process_task(zone, year, month):
    """Fetch and convert one zone-month. Returns (zone_code, year, month, prayer_times) or None."""
    code = zone['code']
    out_dir = os.path.join(ROOT, "data", "prayer-times", "ID", code)
    out_path = os.path.join(out_dir, f"{year}-{month:02d}.json")

    if os.path.exists(out_path):
        return "skipped"

    records = fetch_month(zone['state'], zone['location'], month, year)
    if not records:
        return "empty"

    prayer_times = []
    for r in records:
        prayer_times.append({
            "date": r["tanggal_lengkap"],
            "imsak": r["imsak"],
            "fajr": r["subuh"],
            "syuruk": r["terbit"],
            "dhuhr": r["dzuhur"],
            "asr": r["ashar"],
            "maghrib": r["maghrib"],
            "isha": r["isya"],
        })

    # Validate
    for pt in prayer_times:
        times = [pt['imsak'], pt['fajr'], pt['syuruk'], pt['dhuhr'], pt['asr'], pt['maghrib'], pt['isha']]
        for i in range(len(times) - 1):
            if times[i] >= times[i + 1]:
                print(f"  WARNING: {code} {pt['date']}: times not in order")
                break

    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(prayer_times, f, indent=2)
        f.write('\n')

    return "written"


def main():
    if len(sys.argv) > 1:
        years = [int(sys.argv[1])]
    else:
        now = datetime.now()
        years = [now.year, now.year + 1]

    zones = parse_zones()
    print(f"Found {len(zones)} zones, fetching years: {[str(y) for y in years]}")

    # Build task list
    tasks = []
    for zone in zones:
        for year in years:
            for month in range(1, 13):
                tasks.append((zone, year, month))

    print(f"Total tasks: {len(tasks)}")

    total_written = 0
    total_skipped = 0
    total_empty = 0
    completed = 0

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(process_task, z, y, m): (z, y, m) for z, y, m in tasks}
        for future in as_completed(futures):
            result = future.result()
            completed += 1
            if result == "written":
                total_written += 1
            elif result == "skipped":
                total_skipped += 1
            elif result == "empty":
                total_empty += 1

            if completed % 500 == 0:
                print(f"  Progress: {completed}/{len(tasks)} ({total_written} written, {total_skipped} skipped, {total_empty} empty)")

    print(f"\nDone: {total_written} written, {total_skipped} skipped, {total_empty} empty")


if __name__ == '__main__':
    main()
