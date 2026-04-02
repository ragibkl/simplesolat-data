#!/usr/bin/env python3
"""
Fetch KHEU (Brunei) prayer times from Taqwim PDF.

Downloads the yearly Taqwim PDF from mora.gov.bn, extracts prayer times,
and writes to data/prayer-times/BN/{zone}/{year}-{month}.json.

Base times are for BRN01/BRN04. Zone offsets:
  BRN01: 0 min (Brunei-Muara)
  BRN02: +1 min (Tutong)
  BRN03: +3 min (Belait)
  BRN04: 0 min (Temburong)

Usage: python3 scripts/fetch_kheu.py
"""

import json
import os
import re
import subprocess
import sys

import pdfplumber

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES_YAML = os.path.join(ROOT, "sources", "kheu", "sources.yaml")
CACHE_DIR = os.path.join(ROOT, "sources", "kheu", "pdfs")

ZONES = [
    {"code": "BRN01", "offset": 0},
    {"code": "BRN02", "offset": 1},
    {"code": "BRN03", "offset": 3},
    {"code": "BRN04", "offset": 0},
]

# Month pages in the Taqwim PDF (0-indexed)
# Pages 0-1 are cover/info, pages 2-13 are Jan-Dec
MONTH_PAGES = {
    "01": 2, "02": 3, "03": 4, "04": 5,
    "05": 6, "06": 7, "07": 8, "08": 9,
    "09": 10, "10": 11, "11": 12, "12": 13,
}

DAYS_IN_MONTH = {
    "01": 31, "02": None, "03": 31, "04": 30,
    "05": 31, "06": 30, "07": 31, "08": 31,
    "09": 30, "10": 31, "11": 30, "12": 31,
}


def parse_sources_yaml(path):
    """Parse sources.yaml."""
    entries = []
    current = {}
    with open(path) as f:
        for line in f:
            line = line.rstrip()
            if not line or line.startswith('#') or line.strip() == 'pdfs:':
                continue
            m = re.match(r'\s+- year:\s+"?([^"]+)"?', line)
            if m:
                if current:
                    entries.append(current)
                current = {'year': m.group(1)}
                continue
            m = re.match(r'\s+url:\s+(.+)', line)
            if m:
                current['url'] = m.group(1)
    if current:
        entries.append(current)
    return entries


def download_pdf(url, filepath):
    """Download PDF if not cached."""
    if os.path.exists(filepath):
        return True
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    result = subprocess.run(["curl", "-sL", url, "-o", filepath], capture_output=True)
    if result.returncode != 0 or os.path.getsize(filepath) < 10000:
        print(f"  FAILED: {url}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return False
    return True


def parse_dot_time(time_str, is_pm):
    """Convert dot-separated time (4.55, 12.25) to HH:MM 24-hour."""
    time_str = time_str.strip()
    parts = time_str.split('.')
    h = int(parts[0])
    m = int(parts[1])
    if is_pm and h < 12:
        h += 12
    return f"{h:02d}:{m:02d}"


def add_minutes(time_24h, minutes):
    """Add minutes to a HH:MM time string."""
    if minutes == 0:
        return time_24h
    h, m = map(int, time_24h.split(':'))
    total = h * 60 + m + minutes
    return f"{total // 60:02d}:{total % 60:02d}"


def is_leap_year(year):
    y = int(year)
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def extract_month(pdf, year, month, page_idx):
    """Extract prayer times from a single month page."""
    page = pdf.pages[page_idx]
    text = page.extract_text()

    records = []
    days_expected = DAYS_IN_MONTH[month]
    if month == "02":
        days_expected = 29 if is_leap_year(year) else 28

    # Parse lines that contain prayer time data
    # Pattern: day_num day_name [hijri] imsak suboh syuruk doha zohor asar maghrib isyak
    # Two columns side by side, so a line may have data for two days
    time_pattern = r'(\d{1,2}\.\d{2})'

    for line in text.split('\n'):
        # Fix doubled characters from PDF rendering
        # "55..0066" -> "5.06", "1122..3355" -> "12.35"
        line = re.sub(r'(\d)(\d)\2(\d)\3\.\.(\d)\4(\d)\5', lambda m: f'{m.group(1)}{m.group(2)}.{m.group(4)}{m.group(5)}', line)
        line = re.sub(r'(\d)\1\.\.(\d)\2(\d)\3', lambda m: f'{m.group(1)}.{m.group(2)}{m.group(3)}', line)

        # Find all times in the line
        times = re.findall(time_pattern, line)
        if len(times) < 8:
            continue

        # Find all day numbers at the start of day entries
        # Match day numbers that precede a day name
        day_entries = re.findall(
            r'(?:^|(?<=\s))(\d{1,2})\s+(?:Isnin|Selasa|Rabu|Khamis|Jumaat|Sabtu|Ahad)',
            line
        )

        if len(day_entries) >= 2 and len(times) >= 16:
            # Two days on this line
            for i, day_str in enumerate(day_entries[:2]):
                day = int(day_str)
                if day < 1 or day > 31:
                    continue
                t = times[i * 8:(i + 1) * 8]
                if len(t) < 8:
                    continue
                records.append((day, t))
        elif len(day_entries) >= 1 and len(times) >= 8:
            # One day on this line
            day = int(day_entries[0])
            if 1 <= day <= 31:
                records.append((day, times[:8]))

    # Deduplicate and sort
    seen = set()
    unique_records = []
    for day, times in records:
        if day not in seen:
            seen.add(day)
            unique_records.append((day, times))
    unique_records.sort(key=lambda x: x[0])

    # Convert to prayer time dicts
    prayer_times = []
    for day, t in unique_records:
        # t = [imsak, suboh, syuruk, doha, zohor, asar, maghrib, isyak]
        try:
            imsak = parse_dot_time(t[0], is_pm=False)
            fajr = parse_dot_time(t[1], is_pm=False)
            syuruk = parse_dot_time(t[2], is_pm=False)
            # t[3] is doha, skip
            dhuhr = parse_dot_time(t[4], is_pm=True)
            asr = parse_dot_time(t[5], is_pm=True)
            maghrib = parse_dot_time(t[6], is_pm=True)
            isha = parse_dot_time(t[7], is_pm=True)
        except (ValueError, IndexError) as e:
            print(f"  WARNING: day {day}: {e}")
            continue

        date = f"{year}-{month}-{day:02d}"
        prayer_times.append({
            "date": date,
            "imsak": imsak,
            "fajr": fajr,
            "syuruk": syuruk,
            "dhuhr": dhuhr,
            "asr": asr,
            "maghrib": maghrib,
            "isha": isha,
        })

    if len(prayer_times) != days_expected:
        print(f"  WARNING: {year}-{month}: got {len(prayer_times)} days, expected {days_expected}")

    return prayer_times


def apply_zone_offset(prayer_times, offset):
    """Apply minute offset to all prayer times."""
    if offset == 0:
        return prayer_times
    result = []
    for pt in prayer_times:
        result.append({
            "date": pt["date"],
            "imsak": add_minutes(pt["imsak"], offset),
            "fajr": add_minutes(pt["fajr"], offset),
            "syuruk": add_minutes(pt["syuruk"], offset),
            "dhuhr": add_minutes(pt["dhuhr"], offset),
            "asr": add_minutes(pt["asr"], offset),
            "maghrib": add_minutes(pt["maghrib"], offset),
            "isha": add_minutes(pt["isha"], offset),
        })
    return result


def validate_records(records):
    """Validate prayer time records."""
    errors = 0
    for r in records:
        times = [r['imsak'], r['fajr'], r['syuruk'], r['dhuhr'], r['asr'], r['maghrib'], r['isha']]
        for i in range(len(times) - 1):
            if times[i] >= times[i + 1]:
                print(f"  WARNING: {r['date']}: times not in order")
                errors += 1
                break
    return errors == 0


def main():
    if not os.path.exists(SOURCES_YAML):
        print(f"Sources file not found: {SOURCES_YAML}")
        sys.exit(1)

    entries = parse_sources_yaml(SOURCES_YAML)
    print(f"Found {len(entries)} PDF sources")

    total_written = 0
    total_skipped = 0

    for entry in entries:
        year = entry['year']
        url = entry['url']

        # Download PDF
        pdf_path = os.path.join(CACHE_DIR, f"taqwim-{year}.pdf")
        print(f"Downloading Taqwim {year}...")
        if not download_pdf(url, pdf_path):
            continue

        pdf = pdfplumber.open(pdf_path)

        for month, page_idx in sorted(MONTH_PAGES.items()):
            if page_idx >= len(pdf.pages):
                print(f"  SKIP: page {page_idx} not in PDF")
                continue

            # Check if all zones already have this month
            all_exist = all(
                os.path.exists(os.path.join(
                    ROOT, "data", "prayer-times", "BN", z["code"], f"{year}-{month}.json"
                ))
                for z in ZONES
            )
            if all_exist:
                total_skipped += len(ZONES)
                continue

            # Extract base times
            base_times = extract_month(pdf, year, month, page_idx)
            if not base_times:
                continue

            # Write for each zone with offset
            for zone in ZONES:
                out_dir = os.path.join(ROOT, "data", "prayer-times", "BN", zone["code"])
                out_path = os.path.join(out_dir, f"{year}-{month}.json")
                if os.path.exists(out_path):
                    total_skipped += 1
                    continue

                prayer_times = apply_zone_offset(base_times, zone["offset"])
                validate_records(prayer_times)

                os.makedirs(out_dir, exist_ok=True)
                with open(out_path, 'w') as f:
                    json.dump(prayer_times, f, indent=2)
                    f.write('\n')

                total_written += 1
                print(f"  {zone['code']}/{year}-{month}.json: {len(prayer_times)} days")

        pdf.close()

    print(f"\nDone: {total_written} written, {total_skipped} skipped")


if __name__ == '__main__':
    main()
