# Architecture

## Overview

```
Upstream sources → fetch scripts → data/ (JSON/YAML) → Netlify CDN → mobile app / API
```

Prayer times are fetched from official government sources, normalized to a common JSON format, committed to git, and served as static files via Netlify. The mobile app and API consume data directly from the CDN.

## Data pipeline

### API sources (CI automated)

JAKIM, MUIS, and EQuran have stable APIs. GitHub Actions workflows run on the 27th and 28th of each month, fetch new data if available, commit, and push. Netlify auto-deploys on push.

### PDF/web scrape sources (manual)

KHEU, ACJU, and Diyanet are fetched manually — PDFs change layout, web scrapes break with WAF changes. Run locally, review output, commit via PR.

### Flow

1. Script reads zone list from `data/zones/{CC}.yaml`
2. Checks what data exists in `data/prayer-times/`
3. Fetches only missing months (idempotent)
4. Validates (times in order, correct day count)
5. Writes `data/prayer-times/{CC}/{zone}/{year}-{month}.json`

## Source notes

### JAKIM (Malaysia)
- **Script:** `scripts/fetch_jakim.py`
- **API:** POST `https://www.e-solat.gov.my/index.php?r=esolatApi/takwimsolat`
- Per zone, per year date range, 1s throttle between requests
- 60 zones, times in 24h HH:MM:SS, provides imsak
- Fetches current year + next year by default

### MUIS (Singapore)
- **Script:** `scripts/fetch_muis.py`
- **API:** GET `https://data.gov.sg/api/action/datastore_search`
- Single bulk fetch (~1100 records), needs `MUIS_API_KEY` env var
- Times in 12h without AM/PM — Subuh/Syuruk are AM, rest are PM
- No imsak — derived as subuh - 10 min
- Skips API call if current + next year fully populated

### EQuran (Indonesia)
- **Script:** `scripts/fetch_equran.py`
- **API:** POST `https://equran.id/api/v2/shalat`
- Per zone per month, parallel (10 workers, no rate limiting observed)
- Request body: `{"provinsi": zone.state, "kabkota": zone.location, "bulan": month, "tahun": year}`
- Returns 404 for unavailable data — 3 zone/months filled manually from KEMENAG
- 517 zones, ~7 minutes with parallel fetching

### KHEU (Brunei)
- **Script:** `scripts/fetch_kheu.py`
- **Source:** Taqwim PDF from `https://www.mora.gov.bn`, published annually
- PDF URL in `sources/kheu/sources.yaml`, downloaded on demand
- 4 zones with minute offsets: BRN01 (base), BRN02 (+1min), BRN03 (+3min), BRN04 (base)
- PDF has doubled character artifacts in some months (e.g. `55..0066` → `5.06`, handled in parser)
- Previously used SharePoint API but it was flaky, late to update, and had typos ("112.28", "741")

### ACJU (Sri Lanka)
- **Script:** `scripts/fetch_acju.py`
- **Source:** Per-zone per-month PDFs from `https://www.acju.lk/prayer-times/`, published yearly
- PDF URLs in `sources/acju/sources.yaml`, downloaded in parallel (10 workers)
- 13 zones, times in 12h AM/PM, no imsak — derived as fajr - 10 min
- Some PDFs include Feb 29 in non-leap years (validated and stripped in parser)
- Date format varies between PDFs ("1-Jan" vs "Jun-1")

### Diyanet (Turkey)
- **Script:** `scripts/fetch_diyanet.py`
- **Source:** Web scrape from `https://namazvakitleri.diyanet.gov.tr`
- Headless browser (Playwright) loads one page to extract WAF cookies, then curl fetches all district pages in bulk
- Parses the yearly prayer time HTML table (365 rows per district)
- 867 districts, times in 24h HH:MM, no imsak — derived as fajr - 10 min
- Cookies cached locally in `sources/diyanet/cookies/` (gitignored), valid ~1 hour
- Official REST API exists (`awqatsalah.diyanet.gov.tr`) but requires paper registration and harsh rate limits (5 requests after trial)

## Zone resolution

GPS-to-zone resolution happens on-device in the mobile app:

1. **Country detection** — bundled ADM0 geojson → country ISO code
2. **Shape lookup** — fetch country geojson from CDN → `PolygonLookup.search(lng, lat)` → feature properties
3. **Mapping key** — read `shape_property` from countries.yaml (`shapeName` or `shapeID`) → look up in mapping file → zone code
4. **Zone metadata** — fetch zones YAML → timezone, state, location

### Why shapeID for Turkey

geoBoundaries Turkey ADM2 has 23 duplicate `shapeName` values (e.g. "Kale" exists in both Denizli and Malatya provinces). `shapeName`-keyed mappings can't distinguish them. Turkey uses `shapeID` (unique per feature) as the mapping key instead.

Other countries have no duplicate shapeNames, so they use `shapeName` for simplicity and readability.

The `shape_property` field in `countries.yaml` tells the app which geojson property to use. The app reads it dynamically — no hardcoded assumptions.

## Zone codes

| Country | Convention | Example | Source |
|---------|-----------|---------|--------|
| MY | State abbreviation + number | JHR01, SGR01, WLY01 | JAKIM official codes |
| SG | SGP + number | SGP01 | Single zone |
| ID | Province abbreviation + number | ACH01, JKT01 | Generated |
| BN | BRN + number | BRN01-04 | Generated |
| LK | LK + number | LK01-13 | Generated |
| TR | TR + Diyanet district ID | TR9206, TR9541 | Diyanet official IDs |

Zone codes are stable identifiers — the API and mobile app cache by zone code. Changing a zone code breaks existing caches.

## Mapping generation

`scripts/generate_mappings.py` derives mapping files from zone definitions:

```bash
python3 scripts/generate_mappings.py              # uses geojson datestamp
python3 scripts/generate_mappings.py --date 20260405  # force new datestamp for cache invalidation
```

For each country: reads `data/zones/{CC}.yaml`, inverts the shapes list, writes `data/mappings/{CC}-{adm}-mapping-{date}.json`.

Datestamp defaults to the geojson file's date. Use `--date` to force a new date when fixing mapping bugs (triggers cache invalidation in the app).

## Decisions

- **Per-month files** over per-year — matches upstream publication cadence, simpler idempotency
- **Local HH:MM** over epoch or UTC — source-faithful, human-readable, timezone conversion done by consumers using IANA timezone
- **Netlify over GitHub Pages** — better CDN performance for Malaysian TM ISP users
- **Datestamped filenames** — URL change = cache invalidation, no versioning system needed
- **Pristine geoBoundaries** — geojson files are unmodified from geoBoundaries.org. Disambiguation handled in mapping layer, not by patching source data
- **No workflows for PDF/scrape sources** — extraction is fragile, run locally and review output
