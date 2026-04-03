#!/usr/bin/env python3
"""
Fetch AWQAF (UAE) prayer times from the official AWQAF API.

Uses headless browser to extract auth token, then fetches full year data
via API. Single request returns all 60 areas.

Usage: python3 scripts/fetch_awqaf.py [year]
  Default: current year

Requires: playwright (pip install playwright && playwright install chromium)
"""

import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COOKIE_DIR = os.path.join(ROOT, "sources", "awqaf", "cookies")
API_BASE = "https://mobileappapi.awqaf.gov.ae/APIS/v3"


def get_token():
    """Extract auth token via headless browser. Caches for 15 min."""
    os.makedirs(COOKIE_DIR, exist_ok=True)
    token_file = os.path.join(COOKIE_DIR, "token.json")

    if os.path.exists(token_file):
        age = time.time() - os.path.getmtime(token_file)
        if age < 900:  # 15 min (token valid for 20)
            with open(token_file) as f:
                data = json.load(f)
            print(f"Using cached token ({int(age)}s old)")
            return data["token"]

    print("Extracting fresh token via headless browser...")
    from playwright.sync_api import sync_playwright

    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0",
        )
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.__captured_auth = [];
            const origSetHeader = XMLHttpRequest.prototype.setRequestHeader;
            XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
                if (this._url && this._url.includes('mobileappapi') && name.toLowerCase() === 'authorization') {
                    window.__captured_auth.push(value.replace('Bearer ', ''));
                }
                return origSetHeader.apply(this, arguments);
            };
            const origOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url) {
                this._url = url;
                return origOpen.apply(this, arguments);
            };
        """)

        page.goto("https://www.awqaf.gov.ae/en/Pages/PrayerTimes.aspx", timeout=30000)

        for _ in range(30):
            time.sleep(1)
            captured = page.evaluate("window.__captured_auth")
            if captured:
                break

        browser.close()

    if not captured:
        raise RuntimeError("Failed to extract AWQAF auth token")

    token = captured[0]
    with open(token_file, "w") as f:
        json.dump({"token": token, "timestamp": datetime.now().isoformat()}, f)

    print(f"Got token")
    return token


def fetch_prayer_times(token, date_start, date_end):
    """Fetch prayer times for all areas in a date range."""
    url = f"{API_BASE}/prayer-time/prayertimes/{date_start}/{date_end}"
    result = subprocess.run([
        "curl", "-s", url,
        "-H", f"Authorization: Bearer {token}",
        "-H", "Referer: https://www.awqaf.gov.ae/",
        "-H", "Origin: https://www.awqaf.gov.ae",
    ], capture_output=True, text=True, timeout=60)

    if result.returncode != 0 or not result.stdout:
        return None

    data = json.loads(result.stdout)
    return data.get("prayerData", [])


def parse_time(dt_str):
    """Convert '2026-04-03T04:55:00' to 'HH:MM'."""
    m = re.search(r'T(\d{2}:\d{2})', dt_str)
    return m.group(1) if m else dt_str


def main():
    year = sys.argv[1] if len(sys.argv) > 1 else str(datetime.now().year)

    token = get_token()

    print(f"Fetching prayer times for {year}...")
    records = fetch_prayer_times(token, f"{year}-01-01", f"{year}-12-31")

    if not records:
        print("No data returned")
        return

    areas = set(r["areaNameEn"] for r in records)
    print(f"Got {len(records)} records for {len(areas)} areas")

    # Group by area and month
    by_area_month = defaultdict(list)
    for r in records:
        area_id = r["areaID"]
        date = r["gDate"][:10]  # "2026-04-03"
        month = date[:7]  # "2026-04"
        by_area_month[(area_id, month)].append(r)

    total_written = 0
    total_skipped = 0

    for (area_id, year_month), month_records in sorted(by_area_month.items()):
        zone_code = f"AE{area_id}"
        y, m = year_month.split("-")

        out_dir = os.path.join(ROOT, "data", "prayer-times", "AE", zone_code)
        out_path = os.path.join(out_dir, f"{y}-{m}.json")

        if os.path.exists(out_path):
            total_skipped += 1
            continue

        prayer_times = []
        for r in sorted(month_records, key=lambda x: x["gDate"]):
            fajr = parse_time(r["fajr"])
            # AWQAF sets emsak == fajr. Derive imsak as fajr - 10 min.
            fh, fm = map(int, fajr.split(':'))
            total = fh * 60 + fm - 10
            if total < 0:
                total += 24 * 60
            imsak = f"{total // 60:02d}:{total % 60:02d}"

            prayer_times.append({
                "date": r["gDate"][:10],
                "imsak": imsak,
                "fajr": fajr,
                "syuruk": parse_time(r["shurooq"]),
                "dhuhr": parse_time(r["zuhr"]),
                "asr": parse_time(r["asr"]),
                "maghrib": parse_time(r["maghrib"]),
                "isha": parse_time(r["isha"]),
            })

        # Validate
        for pt in prayer_times:
            times = [pt['imsak'], pt['fajr'], pt['syuruk'], pt['dhuhr'], pt['asr'], pt['maghrib'], pt['isha']]
            for i in range(len(times) - 1):
                if times[i] >= times[i + 1]:
                    print(f"  WARNING: {zone_code} {pt['date']}: times not in order")
                    break

        os.makedirs(out_dir, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(prayer_times, f, indent=2)
            f.write("\n")

        total_written += 1

    print(f"\nDone: {total_written} written, {total_skipped} skipped")

    # Print area summary
    area_info = {}
    for r in records:
        aid = r["areaID"]
        if aid not in area_info:
            area_info[aid] = {
                "id": aid,
                "area": r["areaNameEn"],
                "emirate": r["emirateNameEn"],
            }
    print(f"\nAreas ({len(area_info)}):")
    for aid in sorted(area_info):
        a = area_info[aid]
        print(f"  AE{aid}: {a['emirate']} / {a['area']}")


if __name__ == '__main__':
    main()
