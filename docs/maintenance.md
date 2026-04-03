# Maintenance

## Yearly tasks

### API sources (JAKIM, MUIS, EQuran)

CI handles these automatically. Verify data is flowing:

```bash
python3 scripts/verify_data.py year 2027        # check next year when available
python3 scripts/verify_data.py next-month        # check upcoming month
```

If CI fails, check GitHub Actions logs. Common issues:
- MUIS: API key expired → regenerate at data.gov.sg, update GitHub secret
- EQuran: 404 for specific zones → fill manually from KEMENAG (bimasislam.kemenag.go.id)
- JAKIM: API down → retry via workflow_dispatch, data usually comes back

### PDF sources (KHEU, ACJU)

Run manually when new PDFs are published (typically early in the year).

**KHEU (Brunei):**
1. Check `https://www.mora.gov.bn` for new Taqwim PDF
2. Update URL in `sources/kheu/sources.yaml`
3. Run `python3 scripts/fetch_kheu.py`
4. Review output, commit via PR

**ACJU (Sri Lanka):**
1. Check `https://www.acju.lk/prayer-times/` for new PDFs
2. Save the page HTML locally, extract PDF URLs
3. Update `sources/acju/sources.yaml` with new URLs
4. Run `python3 scripts/fetch_acju.py`
5. Review output, commit via PR

### Web scrape (Diyanet)

Run manually, typically once a year when new data is available.

```bash
python3 scripts/fetch_diyanet.py 2027
```

The script:
1. Launches headless browser to extract WAF cookies (requires Playwright)
2. Curls each district page with cookies (~15 min for 867 districts)
3. Parses yearly HTML tables
4. Writes monthly JSON files

If the WAF blocks you, the script auto-retries cookie extraction. If Diyanet changes their page structure, the HTML parser may need updating.

## Adding a new country

### 1. Find the official source

Look for government or religious authority prayer time data:
- API (best) — stable, automatable
- PDF (good) — authoritative, yearly publication
- Web page (acceptable) — may need scraping

Avoid third-party calculation APIs — the whole point is official published data.

### 2. Create zone definitions

Create `data/zones/{CC}.yaml`:

```yaml
zones:
  - code: XX01
    country: XX
    state: Province Name
    location: District Name
    timezone: Region/City
    shapes:
      - GeoBoundaries shapeName or shapeID
```

**Zone code convention:** country prefix + upstream ID or sequential number.

**Shapes:** match geoBoundaries features to zones. For countries with duplicate district names, use `shapeID` instead of `shapeName`.

### 3. Get geoBoundaries data

Download from [geoBoundaries.org](https://www.geoboundaries.org/):

```
https://www.geoboundaries.org/api/current/gbOpen/{ISO3}/ADM2/
```

Save as `data/geojson/{CC}-adm{N}-geojson-{YYYYMMDD}.json`. Use the file unmodified.

### 4. Generate mapping

```bash
python3 scripts/generate_mappings.py
```

This creates `data/mappings/{CC}-adm{N}-mapping-{date}.json` from the zone shapes.

### 5. Write fetch script

Create `scripts/fetch_{source}.py`. The script should:
- Read zone list from `data/zones/{CC}.yaml`
- Skip existing files (idempotent)
- Validate output (times in order, correct day count per month)
- Handle errors gracefully (log and continue)

### 6. Update countries.yaml

Add entry to `data/countries.yaml`:

```yaml
  - code: XX
    name: Country Name
    source: Authority Name
    geojson: https://simplesolat-data.netlify.app/geojson/{CC}-adm{N}-geojson-{date}.json
    mapping: https://simplesolat-data.netlify.app/mappings/{CC}-adm{N}-mapping-{date}.json
    shape_property: shapeName  # or shapeID if duplicate district names
```

### 7. Fetch and verify

```bash
python3 scripts/fetch_{source}.py
python3 scripts/verify_data.py year 2026 {CC}
python3 scripts/verify_data.py zones  # check for zone code collisions
```

### 8. Submit PR

Include: zones file, geojson, mapping, countries.yaml update, fetch script, source URLs, prayer time data.

## Troubleshooting

### Data gaps (missing zone/months)

```bash
python3 scripts/verify_data.py year 2026          # find gaps
python3 scripts/verify_data.py year 2026 ID       # check specific country
```

If upstream returns no data, fill manually from an alternative official source (e.g. KEMENAG for Indonesia, Diyanet web for Turkey).

### Zone code collisions

```bash
python3 scripts/verify_data.py zones
```

All zone codes must be unique across all countries. If a collision is found, rename the generated zone code (keep the official country's code, rename the other).

### Mapping regeneration

If you update zone shapes or fix a mapping bug:

```bash
python3 scripts/generate_mappings.py                  # same date as geojson
python3 scripts/generate_mappings.py --date 20260405  # new date to bust caches
```

Remember to update the mapping URL in `countries.yaml` if the datestamp changed.

### Diyanet WAF issues

If the headless browser can't extract cookies:
1. Check if the site is up: `curl -I https://namazvakitleri.diyanet.gov.tr`
2. Try clearing the cookie cache: `rm -rf sources/diyanet/cookies/`
3. If consistently blocked, the WAF detection may have changed — check Playwright stealth settings
