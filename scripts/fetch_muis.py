#!/usr/bin/env python3
"""
Fetch MUIS (Singapore) prayer times from data.gov.sg CKAN API.

Single bulk fetch, writes to data/prayer-times/SG/SGP01/{year}-{month}.json.
Requires MUIS_API_KEY env var for higher rate limits.

Usage: python3 scripts/fetch_muis.py
"""

import json
import os
import re
import sys
from collections import defaultdict
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_URL = "https://data.gov.sg/api/action/datastore_search"
RESOURCE_ID = "d_a6a206cba471fe04b62dd886ef5eaf22"
ZONE_CODE = "SGP01"


def parse_time_12h(time_str, is_pm):
    """Convert MUIS time (12-hour without AM/PM) to HH:MM 24-hour."""
    h, m = map(int, time_str.strip().split(':'))
    if is_pm and h < 12:
        h += 12
    return f"{h:02d}:{m:02d}"


def subtract_minutes(time_24h, minutes):
    """Subtract minutes from a HH:MM time string."""
    h, m = map(int, time_24h.split(':'))
    total = h * 60 + m - minutes
    if total < 0:
        total += 24 * 60
    return f"{total // 60:02d}:{total % 60:02d}"


def fetch_all_records():
    """Fetch all prayer time records from MUIS API."""
    api_key = os.environ.get("MUIS_API_KEY", "")

    url = f"{API_URL}?resource_id={RESOURCE_ID}&limit=1100"
    req = Request(url, headers={"User-Agent": "Simplesolat/1.0"})
    if api_key:
        req.add_header("x-api-key", api_key)

    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    if not data.get("success"):
        raise RuntimeError(f"MUIS API error: {data}")

    return data["result"]["records"]


def main():
    api_key = os.environ.get("MUIS_API_KEY", "")
    if not api_key:
        print("WARNING: MUIS_API_KEY not set, may be rate limited")

    print("Fetching MUIS prayer times...")
    records = fetch_all_records()
    print(f"  Fetched {len(records)} records")

    # Group by year-month
    by_month = defaultdict(list)
    for r in records:
        date = r["Date"]  # "2024-01-01"
        year_month = date[:7]  # "2024-01"
        by_month[year_month].append(r)

    total_written = 0
    total_skipped = 0

    for year_month in sorted(by_month.keys()):
        year, month = year_month.split("-")
        out_dir = os.path.join(ROOT, "data", "prayer-times", "SG", ZONE_CODE)
        out_path = os.path.join(out_dir, f"{year}-{month}.json")

        if os.path.exists(out_path):
            total_skipped += 1
            continue

        month_records = sorted(by_month[year_month], key=lambda r: r["Date"])

        prayer_times = []
        for r in month_records:
            subuh = parse_time_12h(r["Subuh"], is_pm=False)
            syuruk = parse_time_12h(r["Syuruk"], is_pm=False)
            zohor = parse_time_12h(r["Zohor"], is_pm=True)
            asar = parse_time_12h(r["Asar"], is_pm=True)
            maghrib = parse_time_12h(r["Maghrib"], is_pm=True)
            isyak = parse_time_12h(r["Isyak"], is_pm=True)
            imsak = subtract_minutes(subuh, 10)

            prayer_times.append({
                "date": r["Date"],
                "imsak": imsak,
                "fajr": subuh,
                "syuruk": syuruk,
                "dhuhr": zohor,
                "asr": asar,
                "maghrib": maghrib,
                "isha": isyak,
            })

        # Validate
        errors = 0
        for pt in prayer_times:
            times = [pt['imsak'], pt['fajr'], pt['syuruk'], pt['dhuhr'], pt['asr'], pt['maghrib'], pt['isha']]
            for i in range(len(times) - 1):
                if times[i] >= times[i + 1]:
                    print(f"  WARNING: {pt['date']}: times not in order")
                    errors += 1
                    break

        os.makedirs(out_dir, exist_ok=True)
        with open(out_path, 'w') as f:
            json.dump(prayer_times, f, indent=2)
            f.write('\n')

        total_written += 1
        print(f"  SGP01/{year}-{month}.json: {len(prayer_times)} days")

    print(f"\nDone: {total_written} written, {total_skipped} skipped")


if __name__ == '__main__':
    main()
