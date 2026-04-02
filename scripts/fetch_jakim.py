#!/usr/bin/env python3
"""
Fetch JAKIM (Malaysia) prayer times from e-solat.gov.my.

Fetches per zone per year, splits into monthly files.
1s throttle between requests. Writes to data/prayer-times/MY/{zone}/{year}-{month}.json.

Usage: python3 scripts/fetch_jakim.py [year]
  Default: current year and next year
"""

import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.parse import urlencode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_URL = "https://www.e-solat.gov.my/index.php"

MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


def parse_zones():
    """Read MY zone codes from data/zones/MY.yaml."""
    zones = []
    zones_path = os.path.join(ROOT, "data", "zones", "MY.yaml")
    with open(zones_path) as f:
        for line in f:
            m = re.match(r'\s+- code:\s+(\S+)', line)
            if m:
                zones.append(m.group(1))
    return zones


def parse_jakim_date(date_str):
    """Convert '01-Jan-2026' to '2026-01-01'."""
    m = re.match(r'(\d{2})-(\w{3})-(\d{4})', date_str)
    if not m:
        raise ValueError(f"Cannot parse date: {date_str}")
    day = m.group(1)
    month = MONTHS[m.group(2)]
    year = m.group(3)
    return f"{year}-{month}-{day}"


def parse_time(time_str):
    """Convert 'HH:MM:SS' to 'HH:MM'."""
    return time_str[:5]


def fetch_zone_year(zone_code, year):
    """Fetch a full year of prayer times for a zone."""
    params = urlencode({
        "r": "esolatApi/takwimsolat",
        "period": "duration",
        "zone": zone_code,
    })
    url = f"{API_URL}?{params}"
    body = urlencode({
        "datestart": f"{year}-01-01",
        "dateend": f"{year}-12-31",
    }).encode()

    req = Request(url, data=body, headers={
        "User-Agent": "Simplesolat/1.0",
        "Content-Type": "application/x-www-form-urlencoded",
    })

    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    if data.get("status") != "OK!":
        raise RuntimeError(f"JAKIM API error for {zone_code}: {data.get('status')}")

    return data["prayerTime"]


def main():
    if len(sys.argv) > 1:
        years = [sys.argv[1]]
    else:
        now = datetime.now()
        years = [str(now.year), str(now.year + 1)]

    zones = parse_zones()
    print(f"Found {len(zones)} zones, fetching years: {', '.join(years)}")

    total_written = 0
    total_skipped = 0
    total_fetched = 0

    for year in years:
        for zone_code in zones:
            # Check if all 12 months already exist
            out_dir = os.path.join(ROOT, "data", "prayer-times", "MY", zone_code)
            all_exist = all(
                os.path.exists(os.path.join(out_dir, f"{year}-{m:02d}.json"))
                for m in range(1, 13)
            )
            if all_exist:
                total_skipped += 12
                continue

            # Throttle
            if total_fetched > 0:
                time.sleep(1)

            # Fetch
            try:
                records = fetch_zone_year(zone_code, year)
                total_fetched += 1
            except Exception as e:
                print(f"  ERROR: {zone_code}/{year}: {e}")
                continue

            # Group by month
            by_month = defaultdict(list)
            for r in records:
                date = parse_jakim_date(r["date"])
                month = date[5:7]
                by_month[month].append({
                    "date": date,
                    "imsak": parse_time(r["imsak"]),
                    "fajr": parse_time(r["fajr"]),
                    "syuruk": parse_time(r["syuruk"]),
                    "dhuhr": parse_time(r["dhuhr"]),
                    "asr": parse_time(r["asr"]),
                    "maghrib": parse_time(r["maghrib"]),
                    "isha": parse_time(r["isha"]),
                })

            # Write per-month files
            for month in sorted(by_month.keys()):
                out_path = os.path.join(out_dir, f"{year}-{month}.json")
                if os.path.exists(out_path):
                    total_skipped += 1
                    continue

                prayer_times = sorted(by_month[month], key=lambda r: r["date"])

                # Validate
                for pt in prayer_times:
                    times = [pt['imsak'], pt['fajr'], pt['syuruk'], pt['dhuhr'], pt['asr'], pt['maghrib'], pt['isha']]
                    for i in range(len(times) - 1):
                        if times[i] >= times[i + 1]:
                            print(f"  WARNING: {zone_code} {pt['date']}: times not in order")
                            break

                os.makedirs(out_dir, exist_ok=True)
                with open(out_path, 'w') as f:
                    json.dump(prayer_times, f, indent=2)
                    f.write('\n')

                total_written += 1

            print(f"  {zone_code}/{year}: {len(records)} days → {len(by_month)} months")

    print(f"\nDone: {total_written} written, {total_skipped} skipped, {total_fetched} API calls")


if __name__ == '__main__':
    main()
