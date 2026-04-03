#!/usr/bin/env python3
"""
Verify prayer time data integrity.

Runs all checks and reports a summary:
- Zone code collisions across all countries
- Next month data availability
- Prayer time ordering (imsak < fajr < syuruk < dhuhr < asr < maghrib < isha)
- Day count per month

Usage:
  python3 scripts/verify_data.py              # check all countries, current year
  python3 scripts/verify_data.py 2026         # check specific year
  python3 scripts/verify_data.py 2026 MY ID   # check specific year and countries

Exits with code 1 if any issues found.
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def discover_countries():
    """Find all country codes from zone files in data/zones/."""
    zones_dir = os.path.join(ROOT, "data", "zones")
    countries = {}
    for f in sorted(os.listdir(zones_dir)):
        if f.endswith('.yaml'):
            cc = f.replace('.yaml', '')
            countries[cc] = os.path.join("data", "zones", f)
    return countries


def parse_zone_codes(path):
    """Read zone codes from a zones YAML file."""
    zones = []
    with open(os.path.join(ROOT, path)) as f:
        for line in f:
            m = re.match(r'\s+- code:\s+(\S+)', line)
            if m:
                zones.append(m.group(1))
    return zones


def check_collisions(country_files):
    """Check for zone code collisions across all countries."""
    all_codes = []
    for cc, zones_file in country_files.items():
        for code in parse_zone_codes(zones_file):
            all_codes.append((code, cc))

    seen = defaultdict(list)
    for code, cc in all_codes:
        seen[code].append(cc)

    collisions = {k: v for k, v in seen.items() if len(v) > 1}
    return len(all_codes), collisions


def check_next_month(country_files, countries_filter):
    """Check that next month's data exists for all zones."""
    today = datetime.now()
    next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    year = next_month.strftime('%Y')
    month = next_month.strftime('%m')

    ok = 0
    missing = []
    for cc, zones_file in country_files.items():
        if countries_filter and cc not in countries_filter:
            continue
        zones = parse_zone_codes(zones_file)
        for zone in zones:
            path = os.path.join(ROOT, "data", "prayer-times", cc, zone, f"{year}-{month}.json")
            if os.path.exists(path):
                ok += 1
            else:
                missing.append(f"{cc}/{zone}/{year}-{month}")
    return year, month, ok, missing


def check_year_data(country_files, year, countries_filter):
    """Check all 12 months for a given year."""
    ok = 0
    missing = []
    for cc, zones_file in country_files.items():
        if countries_filter and cc not in countries_filter:
            continue
        zones = parse_zone_codes(zones_file)
        for zone in zones:
            for m in range(1, 13):
                path = os.path.join(ROOT, "data", "prayer-times", cc, zone, f"{year}-{m:02d}.json")
                if os.path.exists(path):
                    ok += 1
                else:
                    missing.append(f"{cc}/{zone}/{year}-{m:02d}")
    return ok, missing


def check_prayer_order(countries_filter):
    """Validate prayer time ordering in all JSON files."""
    errors = []
    files_checked = 0
    prayer_dir = os.path.join(ROOT, "data", "prayer-times")

    for cc in sorted(os.listdir(prayer_dir)):
        if countries_filter and cc not in countries_filter:
            continue
        cc_dir = os.path.join(prayer_dir, cc)
        if not os.path.isdir(cc_dir):
            continue
        for zone in sorted(os.listdir(cc_dir)):
            zone_dir = os.path.join(cc_dir, zone)
            if not os.path.isdir(zone_dir):
                continue
            for f in sorted(os.listdir(zone_dir)):
                if not f.endswith('.json'):
                    continue
                path = os.path.join(zone_dir, f)
                with open(path) as fh:
                    data = json.load(fh)
                files_checked += 1
                for r in data:
                    times = [r['imsak'], r['fajr'], r['syuruk'], r['dhuhr'], r['asr'], r['maghrib'], r['isha']]
                    # imsak <= fajr is allowed (some authorities set them equal)
                    # all others must be strictly ascending
                    if times[0] > times[1]:
                        errors.append(f"{cc}/{zone}/{f} {r['date']}: imsak > fajr")
                        continue
                    for i in range(1, len(times) - 1):
                        if times[i] >= times[i + 1]:
                            errors.append(f"{cc}/{zone}/{f} {r['date']}: order error")
                            break
    return files_checked, errors


def check_day_counts(countries_filter):
    """Validate day counts per month."""
    issues = []
    prayer_dir = os.path.join(ROOT, "data", "prayer-times")

    for cc in sorted(os.listdir(prayer_dir)):
        if countries_filter and cc not in countries_filter:
            continue
        cc_dir = os.path.join(prayer_dir, cc)
        if not os.path.isdir(cc_dir):
            continue
        for zone in sorted(os.listdir(cc_dir)):
            zone_dir = os.path.join(cc_dir, zone)
            if not os.path.isdir(zone_dir):
                continue
            for f in sorted(os.listdir(zone_dir)):
                if not f.endswith('.json'):
                    continue
                path = os.path.join(zone_dir, f)
                with open(path) as fh:
                    data = json.load(fh)
                year = int(f[:4])
                month = int(f[5:7])
                if month == 12:
                    expected = (date(year + 1, 1, 1) - date(year, month, 1)).days
                else:
                    expected = (date(year, month + 1, 1) - date(year, month, 1)).days
                if len(data) != expected:
                    issues.append(f"{cc}/{zone}/{f}: {len(data)} days, expected {expected}")
    return issues


def main():
    country_files = discover_countries()

    # Parse args
    year = str(datetime.now().year)
    countries_filter = set()
    for arg in sys.argv[1:]:
        if arg.isdigit() and len(arg) == 4:
            year = arg
        elif arg.upper() in country_files:
            countries_filter.add(arg.upper())

    has_issues = False

    # 1. Zone collisions
    total_zones, collisions = check_collisions(country_files)
    if collisions:
        print(f"FAIL  Zone collisions: {len(collisions)}")
        for code, ccs in sorted(collisions.items()):
            print(f"        {code}: {', '.join(ccs)}")
        has_issues = True
    else:
        print(f"OK    Zone collisions: none ({total_zones} zones)")

    # 2. Next month
    nm_year, nm_month, nm_ok, nm_missing = check_next_month(country_files, countries_filter)
    if nm_missing:
        print(f"FAIL  Next month ({nm_year}-{nm_month}): {len(nm_missing)} zones missing")
        for m in nm_missing[:5]:
            print(f"        {m}")
        if len(nm_missing) > 5:
            print(f"        ... and {len(nm_missing) - 5} more")
        has_issues = True
    else:
        print(f"OK    Next month ({nm_year}-{nm_month}): {nm_ok} zones complete")

    # 3. Year completeness
    yr_ok, yr_missing = check_year_data(country_files, year, countries_filter)
    if yr_missing:
        # Group by country
        by_cc = defaultdict(int)
        for m in yr_missing:
            by_cc[m.split('/')[0]] += 1
        summary = ", ".join(f"{cc}: {n}" for cc, n in sorted(by_cc.items()))
        print(f"WARN  Year {year}: {len(yr_missing)} files missing ({summary})")
    else:
        print(f"OK    Year {year}: {yr_ok} files complete")

    # 4. Prayer time ordering
    files_checked, order_errors = check_prayer_order(countries_filter)
    if order_errors:
        print(f"FAIL  Prayer order: {len(order_errors)} errors in {files_checked} files")
        for e in order_errors[:5]:
            print(f"        {e}")
        if len(order_errors) > 5:
            print(f"        ... and {len(order_errors) - 5} more")
        has_issues = True
    else:
        print(f"OK    Prayer order: {files_checked} files checked")

    # 5. Day counts
    day_issues = check_day_counts(countries_filter)
    if day_issues:
        print(f"WARN  Day counts: {len(day_issues)} partial months")
        for d in day_issues[:5]:
            print(f"        {d}")
        if len(day_issues) > 5:
            print(f"        ... and {len(day_issues) - 5} more")
    else:
        print(f"OK    Day counts: all correct")

    if has_issues:
        sys.exit(1)


if __name__ == '__main__':
    main()
