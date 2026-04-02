#!/usr/bin/env python3
"""
Extract ACJU prayer times from PDF files.

Reads sources/acju/sources.yaml for PDF URLs, downloads if not present,
extracts prayer times, and writes to data/prayer-times/LK/{zone}/{year}-{month}.json.

Usage: python3 scripts/extract_acju.py
"""

import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date as Date

import pdfplumber

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES_YAML = os.path.join(ROOT, "sources", "acju", "sources.yaml")
CACHE_DIR = os.path.join(ROOT, "sources", "acju", "pdfs")


def parse_sources_yaml(path):
    """Parse sources.yaml without pyyaml. Returns list of {zone, year, month, url}."""
    entries = []
    current = {}
    with open(path) as f:
        for line in f:
            line = line.rstrip()
            if not line or line.startswith('#') or line.strip() == 'pdfs:':
                continue
            m = re.match(r'\s+- zone:\s+(.+)', line)
            if m:
                if current:
                    entries.append(current)
                current = {'zone': m.group(1)}
                continue
            m = re.match(r'\s+(\w+):\s+"?([^"]+)"?', line)
            if m:
                current[m.group(1)] = m.group(2)
    if current:
        entries.append(current)
    return entries


def download_pdf(url, filepath):
    """Download a PDF if not already cached."""
    if os.path.exists(filepath):
        return True
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    result = subprocess.run(["curl", "-sL", url, "-o", filepath], capture_output=True)
    if result.returncode != 0 or os.path.getsize(filepath) < 1000:
        print(f"  FAILED: {url}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return False
    return True


def parse_time_12h(time_str):
    """Convert '5:00 AM' or '12:15 PM' to 'HH:MM' 24-hour format."""
    time_str = time_str.strip()
    # Handle truncated AM/PM from PDF extraction (e.g. "7:05 P" -> "7:05 PM")
    time_str = re.sub(r'\s+P$', ' PM', time_str)
    time_str = re.sub(r'\s+A$', ' AM', time_str)
    m = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM)', time_str, re.IGNORECASE)
    if not m:
        raise ValueError(f"Cannot parse time: {time_str}")
    hour = int(m.group(1))
    minute = int(m.group(2))
    period = m.group(3).upper()
    if period == 'AM' and hour == 12:
        hour = 0
    elif period == 'PM' and hour != 12:
        hour += 12
    return f"{hour:02d}:{minute:02d}"


def subtract_minutes(time_24h, minutes):
    """Subtract minutes from a HH:MM time string."""
    h, m = map(int, time_24h.split(':'))
    total = h * 60 + m - minutes
    if total < 0:
        total += 24 * 60
    return f"{total // 60:02d}:{total % 60:02d}"


def extract_pdf(pdf_path, year, month):
    """Extract prayer times from a single ACJU PDF."""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        tables = page.extract_tables()

    # Find the prayer time table (has DATE, FAJR, etc. headers)
    prayer_table = None
    for table in tables:
        if table and table[0] and len(table[0]) >= 7:
            header = [str(c).strip().upper() if c else '' for c in table[0]]
            if 'DATE' in header and 'FAJR' in header:
                prayer_table = table
                break

    if not prayer_table:
        print(f"  WARNING: No prayer table found in {pdf_path}")
        return None

    records = []
    for row in prayer_table[1:]:
        if not row or not row[0]:
            continue
        date_str = str(row[0]).strip()
        # Parse day from date like "1-Jan" or "Jun-1"
        m = re.match(r'(\d{1,2})-\w+', date_str)
        if not m:
            m = re.match(r'\w+-(\d{1,2})', date_str)
            if not m:
                continue
        day = int(m.group(1))

        try:
            fajr = parse_time_12h(str(row[1]))
            syuruk = parse_time_12h(str(row[2]))
            dhuhr = parse_time_12h(str(row[3]))
            asr = parse_time_12h(str(row[4]))
            maghrib = parse_time_12h(str(row[5]))
            isha = parse_time_12h(str(row[6]))
            imsak = subtract_minutes(fajr, 10)
        except (ValueError, IndexError) as e:
            print(f"  WARNING: Failed to parse row {row}: {e}")
            continue

        # Validate date exists (e.g. skip Feb 29 in non-leap years)
        try:
            Date(int(year), int(month), day)
        except ValueError:
            continue

        date = f"{year}-{month}-{day:02d}"
        records.append({
            "date": date,
            "imsak": imsak,
            "fajr": fajr,
            "syuruk": syuruk,
            "dhuhr": dhuhr,
            "asr": asr,
            "maghrib": maghrib,
            "isha": isha,
        })

    return records


def validate_records(records):
    """Validate prayer time records. Returns True if all valid."""
    errors = []
    for r in records:
        times = [r['imsak'], r['fajr'], r['syuruk'], r['dhuhr'], r['asr'], r['maghrib'], r['isha']]
        for i in range(len(times) - 1):
            if times[i] >= times[i + 1]:
                errors.append(f"  {r['date']}: times not in order")
                break
    if errors:
        for e in errors[:3]:
            print(e)
    return len(errors) == 0


def main():
    if not os.path.exists(SOURCES_YAML):
        print(f"Sources file not found: {SOURCES_YAML}")
        sys.exit(1)

    entries = parse_sources_yaml(SOURCES_YAML)
    print(f"Found {len(entries)} PDF sources")

    # Filter to entries that need processing
    to_process = []
    total_skipped = 0
    for entry in entries:
        out_dir = os.path.join(ROOT, "data", "prayer-times", "LK", entry['zone'])
        out_path = os.path.join(out_dir, f"{entry['year']}-{entry['month']}.json")
        if os.path.exists(out_path):
            total_skipped += 1
        else:
            entry['_out_path'] = out_path
            entry['_pdf_path'] = os.path.join(CACHE_DIR, f"{entry['zone']}-{entry['year']}-{entry['month']}.pdf")
            to_process.append(entry)

    if not to_process:
        print(f"\nDone: 0 written, {total_skipped} skipped, 0 failed")
        return

    # Download PDFs in parallel
    print(f"Downloading {len(to_process)} PDFs...")
    os.makedirs(CACHE_DIR, exist_ok=True)

    def _download(entry):
        return entry, download_pdf(entry['url'], entry['_pdf_path'])

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(_download, e) for e in to_process]
        downloaded = []
        for f in as_completed(futures):
            entry, ok = f.result()
            if ok:
                downloaded.append(entry)

    # Extract sequentially
    print(f"Extracting {len(downloaded)} PDFs...")
    total_written = 0
    total_failed = len(to_process) - len(downloaded)

    for entry in downloaded:
        records = extract_pdf(entry['_pdf_path'], entry['year'], entry['month'])
        if not records:
            total_failed += 1
            continue

        if not validate_records(records):
            print(f"  WARNING: validation errors in {entry['zone']}/{entry['year']}-{entry['month']}")

        os.makedirs(os.path.dirname(entry['_out_path']), exist_ok=True)
        with open(entry['_out_path'], 'w') as f:
            json.dump(records, f, indent=2)
            f.write('\n')

        total_written += 1
        print(f"  {entry['zone']}/{entry['year']}-{entry['month']}.json: {len(records)} days")

    print(f"\nDone: {total_written} written, {total_skipped} skipped, {total_failed} failed")


if __name__ == '__main__':
    main()
