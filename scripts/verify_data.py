#!/usr/bin/env python3
"""
Verify prayer time data completeness and zone code integrity.

Modes:
  python3 scripts/verify_data.py next-month          # check next month (used by CI)
  python3 scripts/verify_data.py next-month MY SG    # check next month for specific countries
  python3 scripts/verify_data.py year 2026            # check all 12 months of 2026
  python3 scripts/verify_data.py year 2026 2027       # check 2026 and 2027
  python3 scripts/verify_data.py year 2026 MY ID      # check 2026 for specific countries
  python3 scripts/verify_data.py zones                # check for zone code collisions

Exits with code 1 if any issues found.
"""

import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COUNTRY_FILES = {
    "MY": "data/zones/MY.yaml",
    "SG": "data/zones/SG.yaml",
    "ID": "data/zones/ID.yaml",
    "BN": "data/zones/BN.yaml",
    "LK": "data/zones/LK.yaml",
    "TR": "data/zones/TR.yaml",
    "AE": "data/zones/AE.yaml",
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


def check_months(countries, year_months):
    """Check that all zones have data for the given (year, month) pairs.
    Returns (ok_count, missing list)."""
    total_ok = 0
    all_missing = []

    for country in countries:
        zones_path = os.path.join(ROOT, COUNTRY_FILES.get(country, ""))
        if not os.path.exists(zones_path):
            print(f"  SKIP {country}: no zones file")
            continue

        zones = parse_zone_codes(zones_path)
        country_missing = []

        for zone in zones:
            for year, month in year_months:
                path = os.path.join(ROOT, "data", "prayer-times", country, zone, f"{year}-{month}.json")
                if not os.path.exists(path):
                    country_missing.append(f"{zone}/{year}-{month}")

        if country_missing:
            print(f"  FAIL {country}: {len(country_missing)} missing files")
            for m in country_missing[:10]:
                print(f"    {m}")
            if len(country_missing) > 10:
                print(f"    ... and {len(country_missing) - 10} more")
            all_missing.extend(country_missing)
        else:
            print(f"  OK   {country}: all {len(zones)} zones complete")
            total_ok += len(zones)

    return total_ok, all_missing


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "next-month":
        today = datetime.now()
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        year = next_month.strftime('%Y')
        month = next_month.strftime('%m')

        # Remaining args are optional country filters
        countries = sys.argv[2:] if len(sys.argv) > 2 else list(COUNTRY_FILES.keys())

        print(f"Checking next month: {year}-{month}")
        total_ok, missing = check_months(countries, [(year, month)])

    elif mode == "year":
        # Parse years and optional country filters from remaining args
        years = []
        countries = []
        for arg in sys.argv[2:]:
            if arg.isdigit() and len(arg) == 4:
                years.append(arg)
            elif arg.upper() in COUNTRY_FILES:
                countries.append(arg.upper())

        if not years:
            print("Error: specify at least one year")
            sys.exit(1)

        if not countries:
            countries = list(COUNTRY_FILES.keys())

        year_months = [(y, f"{m:02d}") for y in years for m in range(1, 13)]

        print(f"Checking years: {', '.join(years)} for {', '.join(countries)}")
        total_ok, missing = check_months(countries, year_months)

    elif mode == "zones":
        print("Checking for zone code collisions...")
        all_codes = []
        for cc, zones_file in COUNTRY_FILES.items():
            zones_path = os.path.join(ROOT, zones_file)
            if not os.path.exists(zones_path):
                continue
            for code in parse_zone_codes(zones_path):
                all_codes.append((code, cc))

        seen = defaultdict(list)
        for code, cc in all_codes:
            seen[code].append(cc)

        collisions = {k: v for k, v in seen.items() if len(v) > 1}
        if collisions:
            print(f"  FAIL: {len(collisions)} zone code collisions:")
            for code, countries in sorted(collisions.items()):
                print(f"    {code}: {', '.join(countries)}")
            missing = list(collisions.keys())
        else:
            print(f"  OK: no collisions across {len(all_codes)} zones")
            missing = []
        total_ok = len(all_codes) - len(missing)

    else:
        print(f"Unknown mode: {mode}")
        print(__doc__)
        sys.exit(1)

    print(f"\nTotal: {total_ok} ok, {len(missing)} issues")
    if missing:
        sys.exit(1)


if __name__ == '__main__':
    main()
