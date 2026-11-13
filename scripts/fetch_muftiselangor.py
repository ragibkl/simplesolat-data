#!/usr/bin/env python3
"""
Fetch Selangor's district prayer timetables from Jabatan Mufti Negeri
Selangor (JMNS) and write them as zones MFSGR01-09.

From 2027 the mufti publishes one timetable per district instead of three
zones (JAKIM's SGR01-03). Each district PDF has one page per month with the
columns HARI, day, Hijri day, IMSAK, SUBUH, SYURUQ, ZOHOR, ASAR, MAGHRIB,
ISYA'. There is no Dhuha column, so these zones have no dhuha.

Before 2027 each district zone gets a copy of the JAKIM zone it belonged to
(the `legacy` section of sources.yaml), so the map can point at the district
zones before 1 January without changing anyone's times.

Sources: sources/muftiselangor/sources.yaml. PDFs are cached in
sources/muftiselangor/pdfs/ (not committed).

Usage: python3 scripts/fetch_muftiselangor.py
"""

import calendar
import json
import os
import re
import subprocess
import sys

import pdfplumber
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES_YAML = os.path.join(ROOT, "sources", "muftiselangor", "sources.yaml")
CACHE_DIR = os.path.join(ROOT, "sources", "muftiselangor", "pdfs")
OUT_DIR = os.path.join(ROOT, "data", "prayer-times", "MY")

MONTHS = ["JANUARI", "FEBRUARI", "MAC", "APRIL", "MEI", "JUN", "JULAI",
          "OGOS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DISEMBER"]
DAYS = {"ISNIN", "SELASA", "RABU", "KHAMIS", "JUMAAT", "SABTU", "AHAD"}
FIELDS = ["imsak", "fajr", "syuruk", "dhuhr", "asr", "maghrib", "isha"]
# Always after noon. The 2026 PDFs printed 12-hour times ("1:19", "4:42");
# the 2027 ones print 24-hour times. Zohor is never before 12:00 in Malaysia.
PM_FIELDS = {"dhuhr", "asr", "maghrib", "isha"}
TIME = re.compile(r"^(\d{1,2}):(\d{2})$")


def download(url, path):
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    subprocess.run(["curl", "-sSfL", "-A", "Mozilla/5.0", url, "-o", tmp], check=True)
    with open(tmp, "rb") as f:
        if f.read(5) != b"%PDF-":
            os.remove(tmp)
            raise RuntimeError(f"not a PDF: {url}")
    os.replace(tmp, path)


def to_24h(field, text):
    m = TIME.match(text)
    if not m:
        raise ValueError(f"bad time {text!r}")
    h, mi = int(m.group(1)), int(m.group(2))
    if field in PM_FIELDS and h < 12:
        h += 12
    return f"{h:02d}:{mi:02d}"


def parse_pdf(path, year, district):
    """{month: [entries]} for the whole year, checked against the calendar."""
    months = {}
    for page in pdfplumber.open(path).pages:
        text = page.extract_text() or ""
        m = re.search(r"BULAN\s+([A-Z]+)", text)
        if not m or m.group(1) not in MONTHS:
            continue
        month = MONTHS.index(m.group(1)) + 1
        if f"DAERAH {district}" not in text.replace("\n", " "):
            raise ValueError(f"{path}: {m.group(1)} page is not for {district}")
        if not re.search(rf"\b{year}\b", text):
            raise ValueError(f"{path}: {m.group(1)} page is not for {year}")
        entries = {}
        for line in text.splitlines():
            parts = line.split()
            # HARI, day, [Hijri day: missing when the Hijri month name is
            # wrapped onto its own line], then the 7 times.
            if len(parts) < 9 or parts[0] not in DAYS or not parts[1].isdigit():
                continue
            times = parts[-7:]
            if not all(TIME.match(t) for t in times):
                raise ValueError(f"{path}: can't read line {line!r}")
            day = int(parts[1])
            entry = {"date": f"{year}-{month:02d}-{day:02d}"}
            for field, t in zip(FIELDS, times):
                entry[field] = to_24h(field, t)
            entries[day] = entry
        expected = calendar.monthrange(int(year), month)[1]
        if sorted(entries) != list(range(1, expected + 1)):
            missing = sorted(set(range(1, expected + 1)) - set(entries))
            raise ValueError(f"{path}: {m.group(1)} has {len(entries)} days, missing {missing}")
        for e in entries.values():
            times = [e[f] for f in FIELDS]
            if any(a >= b for a, b in zip(times, times[1:])):
                raise ValueError(f"{path}: {e['date']} times not in order: {times}")
        months[month] = [entries[d] for d in sorted(entries)]
    if sorted(months) != list(range(1, 13)):
        raise ValueError(f"{path}: months found {sorted(months)}, expected 1-12")
    return months


def write(zone, year, month, entries):
    """Write a month file; returns True if it changed."""
    path = os.path.join(OUT_DIR, zone, f"{year}-{month:02d}.json")
    text = json.dumps(entries, indent=2) + "\n"
    if os.path.exists(path):
        with open(path) as f:
            if f.read() == text:
                return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    return True


def copy_legacy(zone, year, source_zone):
    """Copy the JAKIM zone's months for that year as they are (with JAKIM's
    Dhuha: it is the published time for the place until the district
    timetables start)."""
    changed = 0
    for month in range(1, 13):
        path = os.path.join(OUT_DIR, source_zone, f"{year}-{month:02d}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        with open(path) as f:
            entries = json.load(f)
        changed += write(zone, year, month, entries)
    return changed


def main():
    with open(SOURCES_YAML) as f:
        sources = yaml.safe_load(f)

    changed = 0
    for year, zones in (sources.get("legacy") or {}).items():
        for zone, source_zone in zones.items():
            n = copy_legacy(zone, year, source_zone)
            print(f"  {zone}/{year}: copy of {source_zone}, {n} months changed")
            changed += n

    for entry in sources["pdfs"]:
        year, zone, district = entry["year"], entry["zone"], entry["district"]
        path = os.path.join(CACHE_DIR, year, os.path.basename(entry["url"]))
        download(entry["url"], path)
        months = parse_pdf(path, year, district)
        n = sum(write(zone, year, m, months[m]) for m in months)
        print(f"  {zone}/{year} ({district.title()}): 12 months, {n} changed")
        changed += n

    print(f"\nDone: {changed} month files changed")


if __name__ == "__main__":
    main()
