#!/usr/bin/env python3
"""
Verify that next month's prayer time data exists for all zones.

Checks data/prayer-times/{country}/{zone}/{year}-{month}.json for each zone.
Can check a specific country or all countries.

Usage:
  python3 scripts/verify_next_month.py          # check all countries
  python3 scripts/verify_next_month.py MY        # check Malaysia only
  python3 scripts/verify_next_month.py MY SG     # check Malaysia and Singapore
"""

import os
import re
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COUNTRY_FILES = {
    "MY": "data/zones/MY.yaml",
    "SG": "data/zones/SG.yaml",
    "ID": "data/zones/ID.yaml",
    "BN": "data/zones/BN.yaml",
    "LK": "data/zones/LK.yaml",
}


def parse_zone_codes(path):
    """Read zone codes from a zones YAML file."""
    zones = []
    with open(path) as f:
        for line in f:
            m = re.match(r'\s+- code:\s+(\S+)', line)
            if m:
                zones.append(m.group(1))
    return zones


def get_next_month():
    """Get next month's year and month as strings."""
    today = datetime.now()
    next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month.strftime('%Y'), next_month.strftime('%m')


def main():
    year, month = get_next_month()
    countries = sys.argv[1:] if len(sys.argv) > 1 else list(COUNTRY_FILES.keys())

    total_ok = 0
    total_missing = 0
    failed_countries = []

    for country in countries:
        zones_path = os.path.join(ROOT, COUNTRY_FILES.get(country, ""))
        if not os.path.exists(zones_path):
            print(f"  SKIP {country}: no zones file")
            continue

        zones = parse_zone_codes(zones_path)
        missing = []
        for zone in zones:
            path = os.path.join(ROOT, "data", "prayer-times", country, zone, f"{year}-{month}.json")
            if not os.path.exists(path):
                missing.append(zone)

        if missing:
            print(f"  FAIL {country}: {len(missing)}/{len(zones)} zones missing for {year}-{month}")
            for z in missing[:10]:
                print(f"    {z}")
            if len(missing) > 10:
                print(f"    ... and {len(missing) - 10} more")
            total_missing += len(missing)
            failed_countries.append(country)
        else:
            print(f"  OK   {country}: all {len(zones)} zones have data for {year}-{month}")
            total_ok += len(zones)

    print(f"\nTotal: {total_ok} ok, {total_missing} missing")
    if failed_countries:
        sys.exit(1)


if __name__ == '__main__':
    main()
