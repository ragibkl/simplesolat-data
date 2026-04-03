#!/usr/bin/env python3
"""
Fetch Diyanet (Turkey) prayer times from namazvakitleri.diyanet.gov.tr.

Uses headless browser to extract WAF cookies, then curls each district page
to parse the yearly prayer time table from HTML.

Usage: python3 scripts/fetch_diyanet.py [year]
  Default: current year

Requires: playwright (pip install playwright && playwright install chromium)
"""

import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COOKIE_DIR = os.path.join(ROOT, "sources", "diyanet", "cookies")
BASE_URL = "https://namazvakitleri.diyanet.gov.tr/en-US"

CURL_HEADERS = [
    "-H", "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0",
    "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "-H", "Accept-Language: en-US,en;q=0.9",
    "-H", "Referer: https://namazvakitleri.diyanet.gov.tr/en-US",
    "-H", "Sec-Fetch-Dest: document",
    "-H", "Sec-Fetch-Mode: navigate",
    "-H", "Sec-Fetch-Site: same-origin",
]


def get_cookies():
    """Get WAF cookies. Returns cached if fresh, otherwise extracts via headless browser."""
    os.makedirs(COOKIE_DIR, exist_ok=True)
    cookie_file = os.path.join(COOKIE_DIR, "diyanet_cookies.json")

    # Use cached cookies if less than 1 hour old
    if os.path.exists(cookie_file):
        age = time.time() - os.path.getmtime(cookie_file)
        if age < 3600:
            with open(cookie_file) as f:
                data = json.load(f)
            print(f"Using cached cookies ({int(age)}s old)")
            return data["cookie_str"]

    print("Extracting fresh cookies via headless browser...")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0",
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page.goto(f"{BASE_URL}/9206/prayer-time-for-ankara", timeout=60000)
        time.sleep(5)
        page.wait_for_load_state("networkidle", timeout=15000)

        cookies = context.cookies()
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

        browser.close()

    # Cache
    with open(cookie_file, "w") as f:
        json.dump({"cookie_str": cookie_str, "timestamp": datetime.now().isoformat()}, f)

    print(f"Got {len(cookies)} cookies")
    return cookie_str


def fetch_page(url, cookie_str):
    """Fetch a page with cookies via curl. Returns HTML or None."""
    result = subprocess.run(
        ["curl", "-s", "--compressed", url, "-H", f"Cookie: {cookie_str}"] + CURL_HEADERS,
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def get_districts(cookie_str):
    """Parse all provinces and districts from the Diyanet page dropdowns."""
    html = fetch_page(f"{BASE_URL}/9206/prayer-time-for-ankara", cookie_str)
    if not html:
        raise RuntimeError("Failed to fetch main page")

    # Find province select (second select on page)
    selects = re.findall(r'<select[^>]*>(.*?)</select>', html, re.DOTALL)
    if len(selects) < 3:
        raise RuntimeError(f"Expected 3+ selects, found {len(selects)}")

    # Province select is the second one (index 1)
    province_options = re.findall(r'<option[^>]*value="(\d+)"[^>]*>([^<]+)</option>', selects[1])
    print(f"Found {len(province_options)} provinces")

    # For each province, we need to fetch districts
    # But the district select only shows current province's districts
    # Use the page URL pattern instead — district IDs are sequential per province
    # Actually, let's fetch district pages by changing province in the dropdown
    # Simpler: use the search on Diyanet or parse each province page

    # The district list for current province is in the third select
    # To get all districts, we need to iterate provinces via AJAX or fetch each province page
    # Let's use a different approach — fetch the district list from each province page

    districts = []

    for prov_id, prov_name in province_options:
        # Fetch province page to get district dropdown
        # The URL pattern is: /en-US/{district_id}/prayer-time-for-{name}
        # But we need the first district ID for each province
        # Let's try the AJAX endpoint that populates districts
        ajax_html = fetch_page(f"{BASE_URL}/{prov_id}/prayer-time-for-x", cookie_str)
        if not ajax_html:
            print(f"  SKIP {prov_name}: failed to fetch")
            continue

        # Parse district select from this page
        page_selects = re.findall(r'<select[^>]*>(.*?)</select>', ajax_html, re.DOTALL)
        if len(page_selects) < 3:
            continue

        district_options = re.findall(r'<option[^>]*value="(\d+)"[^>]*>([^<]+)</option>', page_selects[2])
        for dist_id, dist_name in district_options:
            districts.append({
                "id": dist_id,
                "province": prov_name.strip(),
                "district": dist_name.strip(),
            })

        print(f"  {prov_name.strip()}: {len(district_options)} districts")
        time.sleep(0.2)  # Be gentle

    return districts


def parse_yearly_table(html):
    """Parse the yearly prayer time table from HTML. Returns list of day records."""
    # Find the yearly table (table with >300 rows)
    tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
    yearly_table = None
    for table in tables:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.DOTALL)
        if len(rows) > 300:
            yearly_table = rows
            break

    if not yearly_table:
        return None

    records = []
    for row in yearly_table[1:]:  # Skip header
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if len(cells) < 8:
            continue

        # cells: [date, hijri, fajr, sun, dhuhr, asr, maghrib, isha]
        date_str = cells[0]  # "01.01.2026"
        m = re.match(r'(\d{2})\.(\d{2})\.(\d{4})', date_str)
        if not m:
            continue

        date = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        fajr = cells[2]
        syuruk = cells[3]
        dhuhr = cells[4]
        asr = cells[5]
        maghrib = cells[6]
        isha = cells[7]

        # Derive imsak as fajr - 10 min
        fh, fm = map(int, fajr.split(':'))
        total = fh * 60 + fm - 10
        if total < 0:
            total += 24 * 60
        imsak = f"{total // 60:02d}:{total % 60:02d}"

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


def fetch_district(district, cookie_str, year):
    """Fetch and parse prayer times for one district. Returns (district, status, records)."""
    dist_id = district["id"]
    slug = district["district"].lower().replace(" ", "-")
    url = f"{BASE_URL}/{dist_id}/prayer-time-for-{slug}"

    # Check if all 12 months already exist
    zone_code = district.get("zone_code")
    if zone_code:
        out_dir = os.path.join(ROOT, "data", "prayer-times", "TR", zone_code)
        all_exist = all(
            os.path.exists(os.path.join(out_dir, f"{year}-{m:02d}.json"))
            for m in range(1, 13)
        )
        if all_exist:
            return district, "skipped", None

    html = fetch_page(url, cookie_str)
    if not html:
        return district, "error", None

    records = parse_yearly_table(html)
    if not records:
        return district, "empty", None

    return district, "ok", records


def main():
    year = sys.argv[1] if len(sys.argv) > 1 else str(datetime.now().year)

    # Step 1: Get cookies
    cookie_str = get_cookies()

    # Step 2: Get district list (or load cached)
    locations_file = os.path.join(ROOT, "sources", "diyanet", "locations.yaml")
    if os.path.exists(locations_file):
        # Parse existing locations
        districts = []
        current = {}
        with open(locations_file) as f:
            for line in f:
                m = re.match(r'\s+- id:\s+"?(\d+)"?', line)
                if m:
                    if current:
                        districts.append(current)
                    current = {"id": m.group(1)}
                    continue
                m = re.match(r'\s+(\w+):\s+(.+)', line)
                if m:
                    current[m.group(1)] = m.group(2).strip().strip('"')
            if current:
                districts.append(current)
        print(f"Loaded {len(districts)} districts from {locations_file}")
    else:
        print("Fetching district list from Diyanet...")
        districts = get_districts(cookie_str)
        # Save locations
        os.makedirs(os.path.dirname(locations_file), exist_ok=True)
        with open(locations_file, "w") as f:
            f.write("# Diyanet prayer time locations\n")
            f.write("# Source: namazvakitleri.diyanet.gov.tr\n")
            f.write("districts:\n")
            for d in districts:
                f.write(f'  - id: "{d["id"]}"\n')
                f.write(f'    province: "{d["province"]}"\n')
                f.write(f'    district: "{d["district"]}"\n')
        print(f"Saved {len(districts)} districts to {locations_file}")

    # Step 3: Fetch prayer times
    print(f"\nFetching prayer times for {year}...")
    total_written = 0
    total_skipped = 0
    total_errors = 0

    # Sequential for now — parallel might trigger WAF
    for i, district in enumerate(districts):
        dist_id = district["id"]
        province = district["province"]
        dist_name = district["district"]
        zone_code = district.get("zone_code", f"TR{dist_id}")

        # Check if all months exist
        out_dir = os.path.join(ROOT, "data", "prayer-times", "TR", zone_code)
        all_exist = all(
            os.path.exists(os.path.join(out_dir, f"{year}-{m:02d}.json"))
            for m in range(1, 13)
        )
        if all_exist:
            total_skipped += 1
            continue

        slug = dist_name.lower().replace(" ", "-").replace("ı", "i").replace("ş", "s").replace("ç", "c").replace("ö", "o").replace("ü", "u").replace("ğ", "g").replace("İ", "i")
        url = f"{BASE_URL}/{dist_id}/prayer-time-for-{slug}"

        html = fetch_page(url, cookie_str)
        if not html:
            print(f"  ERROR: {province}/{dist_name}")
            total_errors += 1
            continue

        records = parse_yearly_table(html)
        if not records:
            print(f"  EMPTY: {province}/{dist_name}")
            total_errors += 1
            continue

        # Group by month and write
        from collections import defaultdict
        by_month = defaultdict(list)
        for r in records:
            month = r["date"][5:7]
            by_month[month].append(r)

        os.makedirs(out_dir, exist_ok=True)
        for month in sorted(by_month.keys()):
            out_path = os.path.join(out_dir, f"{year}-{month}.json")
            if not os.path.exists(out_path):
                prayer_times = sorted(by_month[month], key=lambda r: r["date"])
                with open(out_path, "w") as f:
                    json.dump(prayer_times, f, indent=2)
                    f.write("\n")

        total_written += 1

        if (i + 1) % 50 == 0:
            print(f"  Progress: {i+1}/{len(districts)} ({total_written} written, {total_skipped} skipped)")

        time.sleep(0.3)  # Be gentle with the WAF

    print(f"\nDone: {total_written} districts written, {total_skipped} skipped, {total_errors} errors")


if __name__ == '__main__':
    main()
