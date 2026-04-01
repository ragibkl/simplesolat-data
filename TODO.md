# simplesolat-data — Implementation Plan

## Overview

Centralized prayer times data repository. CI fetches from upstream sources and commits JSON files. The simplesolat-api sync reads from this repo instead of hitting upstream APIs directly. Community can contribute new countries via PRs.

## Directory Structure

```
simplesolat-data/
  data/                          # prayer times JSON (output)
    MY/{zone_code}/{year}-{month}.json   # e.g. data/MY/SGR01/2026-01.json
    SG/SGP01/{year}-{month}.json
    ID/{zone_code}/{year}-{month}.json
    BN/{zone_code}/{year}-{month}.json
    LK/{zone_code}/{year}-{month}.json

  zones/
    zones.yaml                   # all zone definitions (moved from simplesolat-api)

  mappings/                      # mobile zone resolution files
    adm2_zone_mapping_id.json
    adm2_zone_mapping_lk.json
    adm1_zone_mapping_bn.json

  geojson/                       # geoBoundaries files per country (for mobile)
    IDN-ADM2.geojson
    LKA-ADM2.geojson
    BRN-ADM1.geojson

  sources/                       # raw non-API data (PDFs, etc.)
    acju/2026/*.pdf              # ACJU prayer time PDFs

  scripts/                       # fetch & extraction scripts (Rust preferred, polyglot ok)
    fetch_jakim/                 # API → data/MY/
    fetch_muis/                  # API → data/SG/
    fetch_equran/                # API → data/ID/
    fetch_kheu/                  # API → data/BN/
    extract_acju/                # sources/acju/*.pdf → data/LK/

  .github/workflows/
    fetch_jakim.yml              # MY — monthly
    fetch_muis.yml               # SG — monthly
    fetch_equran.yml             # ID — monthly
    fetch_kheu.yml               # BN — end of month (daily last 3 days)
    extract_acju.yml             # LK — yearly
```

## Data Format

Each file is one zone, one month. Array of daily records:

```json
[
  {
    "date": "2026-01-01",
    "imsak": "06:01",
    "fajr": "06:11",
    "syuruk": "07:17",
    "dhuhr": "13:24",
    "asr": "16:30",
    "maghrib": "19:26",
    "isha": "20:35"
  },
  ...
]
```

- Times are HH:MM in local timezone (no seconds, no timezone info)
- Timezone is determined by zone metadata in zones.yaml
- 28–31 records per file (one per day of the month)

## Implementation Steps

### Step 1: Seed initial data
- [ ] Copy zones.yaml from simplesolat-api
- [ ] Copy mapping files from simplesolat-api
- [ ] Copy ACJU JSON files from simplesolat-api (already in data/acju/2026/)
- [ ] Download geoBoundaries files for ID, LK, BN

### Step 2: Write fetch scripts

Preferred language: **Rust** (can reuse existing fetch/parse logic from simplesolat-api repo).
Reference code: https://github.com/ragibkl/simplesolat-api/tree/master/src/api

- [ ] fetch_jakim — POST to e-solat.gov.my, one zone at a time, 1s throttle
- [ ] fetch_muis — GET data.gov.sg CKAN API, single bulk fetch, needs MUIS_API_KEY
- [ ] fetch_equran — POST to equran.id, per zone per month, 200ms throttle
- [ ] fetch_kheu — GET mora.gov.bn SharePoint, date range query, handle pagination
- [ ] extract_acju — read PDFs from sources/acju/ (Python ok here if Rust PDF libs are lacking)

Each script should:
- Check what data already exists in data/
- Only fetch missing months (skip if {year}-{month}.json already exists)
- Write to data/{country}/{zone_code}/{year}-{month}.json
- Validate output before writing (times in order: imsak < fajr < syuruk < dhuhr < asr < maghrib < isha, no gaps in month)
- Retry transient failures (network errors, timeouts) with backoff
- Be idempotent (safe to re-run)
- Handle errors gracefully (log and continue)

### Step 3: GitHub Actions workflows (one per source)

Each source gets its own workflow so failures are isolated and schedules can differ.
All workflows run on the 27th and 28th of each month (idempotent — noop if data already exists).
After fetching, each workflow must verify next month's data exists for all zones — fail loudly if missing.

- [ ] fetch_jakim.yml — schedule: 27th & 28th
- [ ] fetch_muis.yml — schedule: 27th & 28th, bulk fetch, needs MUIS_API_KEY as GitHub secret
- [ ] fetch_equran.yml — schedule: 27th & 28th
- [ ] fetch_kheu.yml — schedule: 27th & 28th
- [ ] extract_acju.yml — schedule: yearly (Jan) or manual when new PDFs are published

All workflows should:
- [ ] Support workflow_dispatch for manual trigger
- [ ] Steps: checkout → run fetch script → verify next month data → commit if changed → push

### Step 4: Update simplesolat-api
- [ ] Rewrite sync to read from simplesolat-data (GitHub raw) instead of upstream APIs
- [ ] Remove upstream API client code (src/api/jakim.rs, muis.rs, equran.rs, kheu.rs, acju.rs)
- [ ] Keep simple JSON parsing (local HH:MM → epoch conversion) + DB upsert
- [ ] Move zones.yaml, mapping files, ACJU data out of simplesolat-api repo
- [ ] Decide sync trigger: API polls on schedule, or CI webhook after data push?

### Step 5: Update simplesolat (mobile)
- [ ] On GPS country detection, check if country has official zones (via API or zones.yaml)
- [ ] If official + no cached geojson for that country → fetch geojson + mapping from simplesolat-data, cache locally
- [ ] Keep MY/SG geojson bundled (core user base), fetch others on demand
- [ ] ADM0 (country detection) stays bundled — small and global
- [ ] Calculated zones (adhan-js) remain the fallback for unsupported countries
- [ ] Adding a new country no longer requires app update — just data repo + API changes

## Upstream API Notes

### JAKIM (Malaysia)
- POST https://www.e-solat.gov.my/index.php?r=esolatApi/takwimsolat
- Per zone, per year date range
- 1s throttle between requests
- 60 zones × 2 years = ~120 requests

### MUIS (Singapore)
- GET https://data.gov.sg/api/action/datastore_search
- Single bulk fetch, ~1100 records
- Needs API key (MUIS_API_KEY) for higher rate limits
- 1 request total

### EQuran (Indonesia)
- POST https://equran.id/api/v2/shalat
- Per zone per month
- 200ms throttle
- 517 zones × 12 months = ~6200 requests per year
- Returns 404 for unavailable data (don't retry)

### KHEU (Brunei)
- GET https://www.mora.gov.bn/_api/web/lists/getbytitle('Waktu%20Sembahyang')/items
- SharePoint REST API, date range query with pagination
- DNS can be flaky
- Dot-separated times (5.04 not 5:04), 12-hour without AM/PM
- Upstream typos: "112.28" (extra digit), "741" (missing dot)
- 4 zones with minute offsets: BRN01 (base), BRN02 (+1min), BRN03 (+3min), BRN04 (base)

### ACJU (Sri Lanka)
- No API — PDFs published yearly at https://www.acju.lk/prayer-times/
- 13 official zones (multiple districts share same times)
- Data from thani-sh/prayer-time-lk GitHub repo (MIT), verified against ACJU PDFs
- Times in minutes-from-midnight format: [300, 382, 735, 937, 1087, 1161]
- No imsak — derive as fajr - 10 min

## Contributing a New Country

1. Find official prayer times source (government authority, PDF, API)
2. Write a script in `scripts/` that outputs JSON in the data format above
3. Add zone definitions to `zones/zones.yaml`
4. Add geoBoundaries mapping to `mappings/`
5. If source is PDF, commit raw PDF to `sources/`
6. Submit PR with all of the above
