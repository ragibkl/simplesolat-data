# simplesolat-data — Project Status

See [README.md](README.md) for data format, usage flows, and API reference.

## Implementation Steps

### Step 1: Seed initial data
- [x] Create countries.yaml with official country definitions and geojson/mapping URLs
- [x] Split zones.yaml into per-country files with shapes and timezone
- [x] Copy and datestamp mapping files (now generated from zones)
- [x] Download and datestamp geoBoundaries files for ID, LK, BN
- [x] Normalize MY geojson to standard shapeName format
- [x] Create mapping generation script (scripts/generate_mappings.py)
- [x] Create sources/acju/sources.yaml with PDF URLs
- [x] Create fetch_acju.py (parallel download + pdfplumber extraction)
- [x] Extract all LK prayer times for 2026 (13 zones × 12 months = 156 files)
- [x] Reorganize all consumable data under data/

### Step 2: Write fetch scripts
- [x] fetch_jakim — POST to e-solat.gov.my, per zone per year, 1s throttle
- [x] fetch_muis — GET data.gov.sg CKAN API, single bulk fetch, needs MUIS_API_KEY
- [x] fetch_equran — POST to equran.id, per zone per month, parallel (10 workers)
- [x] fetch_kheu — extracts from Taqwim PDF (mora.gov.bn), applies zone offsets
- [x] fetch_acju — downloads PDFs from sources.yaml, extracts via pdfplumber

### Step 3: GitHub Actions workflows
- [x] fetch_jakim.yml — cron 27th & 28th + workflow_dispatch
- [x] fetch_muis.yml — cron 27th & 28th + workflow_dispatch, needs MUIS_API_KEY secret
- [x] fetch_equran.yml — cron 27th & 28th + workflow_dispatch
- [x] keepalive.yml — prevents GitHub from disabling scheduled workflows
- KHEU and ACJU: no workflow — PDF extraction is fragile, run locally and review output

### Setup
- [x] Add MUIS_API_KEY as GitHub repository secret
- [x] Enable GitHub Pages (serves data/ at ragibkl.github.io/simplesolat-data/)

### Known data gaps
- [x] EQuran ID: 3 zone/months returned no data (MLK10/2026-01, STA13/2026-09, SMU05/2026-11) — filled manually from KEMENAG
- [x] ACJU LK: Feb 29 in non-leap year 2026 — stripped invalid date, added validation to script

### Step 4: Update simplesolat-api
- [x] Rewrite sync to read from simplesolat-data (GitHub Pages) instead of upstream APIs
- [ ] Remove old upstream API client code
- [ ] New endpoint: GET /countries
- [ ] New endpoint: GET /zones?country=MY

### Step 5: Update simplesolat (mobile)
- [ ] Fetch countries list from API (GET /countries), cache for 1 month
- [ ] On GPS country detection, check if country is in official list
- [ ] If official + no cached geojson → fetch geojson + mapping via URLs from countries list, cache locally
- [ ] Cache geojson/mapping by URL — URL change (datestamp) = new data
- [ ] On countries refresh: compare cached URLs vs new URLs, delete old cached files, fetch new ones
- [ ] ADM0 (country detection) stays bundled — small and global
- [ ] Calculated zones (adhan-js) remain the fallback for unsupported countries
- [ ] Adding a new country no longer requires app update — just data repo + API changes

## Decisions & Rationale

- **Per-month files** over per-year — matches upstream publication cadence, simpler idempotency
- **Local HH:MM** over epoch or UTC — source-faithful, human-readable, timezone conversion done by consumers using IANA timezone from zone metadata
- **PDF over SharePoint API for KHEU** — SharePoint was flaky, late to update, had typos. Taqwim PDF is authoritative, has full year data
- **No workflows for PDF sources** — PDF extraction is fragile (layout changes break parsers), run locally and review output
- **GitHub Pages over API for data serving** — free, CDN-backed, no infrastructure to maintain, outlives API infra
- **Datestamped geojson/mapping filenames** — URL change = cache invalidation, no versioning needed

## Upstream API Notes

### JAKIM (Malaysia)
- POST https://www.e-solat.gov.my/index.php?r=esolatApi/takwimsolat
- Per zone, per year date range, 1s throttle
- 60 zones, times in 24h HH:MM:SS, provides imsak

### MUIS (Singapore)
- GET https://data.gov.sg/api/action/datastore_search
- Single bulk fetch (~1100 records), needs MUIS_API_KEY
- Times in 12h without AM/PM (Subuh/Syuruk=AM, rest=PM), no imsak (derive as subuh-10)

### EQuran (Indonesia)
- POST https://equran.id/api/v2/shalat
- Per zone per month, parallel OK (no rate limiting observed)
- Request body: {"provinsi": zone.state, "kabkota": zone.location, "bulan": month, "tahun": year}
- 3 zone/months return 404 (filled from KEMENAG)

### KHEU (Brunei)
- Taqwim PDF from https://www.mora.gov.bn, published annually
- 4 zones with minute offsets: BRN01 (base), BRN02 (+1min), BRN03 (+3min), BRN04 (base)
- PDF has doubled character artifacts in some months (handled in parser)

### ACJU (Sri Lanka)
- PDFs from https://www.acju.lk/prayer-times/, published yearly (per zone per month)
- 13 zones, times in 12h AM/PM, no imsak (derive as fajr-10)
- Some PDFs have Feb 29 in non-leap years (validated in parser)

## Future Data Source Coverage

### Official sources to investigate (potential integration)

| Country | Authority | Source | Notes |
|---------|-----------|--------|-------|
| Bangladesh | Islamic Foundation | [islamicfoundation.gov.bd](https://islamicfoundation.gov.bd) | Publishes district-level schedules, check if scrapeable |
| Turkey | Diyanet | [awqatsalah.diyanet.gov.tr](https://awqatsalah.diyanet.gov.tr) | Has REST API, heavily rate-limited. Currently calculated on mobile. |
| UAE | IACAD | [iacad.gov.ae](https://www.iacad.gov.ae/en/open-data/prayer-time-open-data) | Open data portal. Currently calculated on mobile. |
| Morocco | Habous Ministry | [habous.gov.ma](https://habous.gov.ma) | Unofficial GitHub scraper exists |

### Worldwide coverage (calculation on mobile via adhan-js)

For countries without official API sources, the mobile app calculates prayer times client-side using [adhan-js](https://github.com/batoulapps/adhan-js) with region-appropriate methods.

**High confidence** — well-defined official method, supported by adhan-js:

| Country | Method | Fajr / Isha | Notes |
|---------|--------|-------------|-------|
| Saudi Arabia | Umm Al-Qura University | 18.5° / 90min | Official govt standard, used by Haramain |
| Egypt | Egyptian General Authority of Survey | 19.5° / 17.5° | Widely used across Africa |
| Qatar | Qatar | 18° / 90min | |
| Kuwait | Kuwait | 18° / 17.5° | |
| Iran | Geophysics Institute Tehran | 17.7° / 14° | |
| US / Canada | ISNA | 15° / 15° | |

**Moderate confidence** — named method, not verified against local authority:

| Country | Method | Fajr / Isha | Notes |
|---------|--------|-------------|-------|
| Turkey | Diyanet | 18° / 17° | Pending official API integration |
| UAE | Dubai | 18.2° / 18.2° | Pending official API integration |
| Jordan | Jordan | 18° / 18° | |
| Algeria | Algerian Ministry | 18° / 17° | |
| Tunisia | Tunisia | 18° / 18° | |
| France | UOIF | 12° / 12° | |
| Pakistan | Karachi | 18° / 18° | Multiple methods used regionally |
| Russia | Russia | 16° / 15° | Regional variation |

**Low confidence** — no documented official method, best guess:

| Country | Best guess | Notes |
|---------|-----------|-------|
| Thailand | MWL or JAKIM-like (20°/18°) | CICOT is official body but method undocumented |
| Philippines | MWL (18°/17°) | NCMF announces Ramadan dates but no prayer times method |
| India | Karachi or MWL | No single authority, varies by region |
| Bangladesh | Karachi (assumed) | Islamic Foundation publishes times but angles undocumented |
| Oman, Bahrain, Yemen, Iraq | MWL (assumed) | Gulf states, no documented methods found |
| Libya, Sudan, Somalia | Egyptian or MWL (assumed) | No documented methods found |
| Maldives | MWL (assumed) | No documented method |
| All other countries | Muslim World League | Default fallback |
