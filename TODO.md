# simplesolat-data — TODO

See [README.md](README.md) for data format, usage flows, and API reference.

## Open issues

- [ ] Diyanet TR: 2 districts under maintenance (TR17876/Çukurova, TR17898/Akköy) — retry when Diyanet fixes
- [ ] Diyanet TR: 2 geoBoundaries shapes unmapped (Hamur, Merkez) — not in Diyanet district list

## Decisions & Rationale

- **Per-month files** over per-year — matches upstream publication cadence, simpler idempotency
- **Local HH:MM** over epoch or UTC — source-faithful, human-readable, timezone conversion done by consumers using IANA timezone from zone metadata
- **PDF over SharePoint API for KHEU** — SharePoint was flaky, late to update, had typos. Taqwim PDF is authoritative, has full year data
- **Web scrape over API for Diyanet** — official API requires paper registration, harsh rate limits. Web scrape gets full year per district from the yearly table
- **No workflows for PDF/scrape sources** — extraction is fragile (layout changes break parsers), run locally and review output
- **Netlify over GitHub Pages** — better CDN performance for Malaysian TM ISP users
- **Datestamped geojson/mapping filenames** — URL change = cache invalidation, no versioning needed
- **shapeID over shapeName for TR** — Turkey has 23 duplicate district names across provinces. shapeID is unique per geoBoundaries feature. Other countries use shapeName (no duplicates)
- **Pristine geoBoundaries** — geojson files are unmodified from geoBoundaries.org. Disambiguation handled in mapping layer, not by patching source data

## Upstream API Notes

Reference for script authors — how each source works and its quirks.

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
- 3 zone/months returned 404 (filled from KEMENAG)

### KHEU (Brunei)
- Taqwim PDF from https://www.mora.gov.bn, published annually
- 4 zones with minute offsets: BRN01 (base), BRN02 (+1min), BRN03 (+3min), BRN04 (base)
- PDF has doubled character artifacts in some months (handled in parser)

### ACJU (Sri Lanka)
- PDFs from https://www.acju.lk/prayer-times/, published yearly (per zone per month)
- 13 zones, times in 12h AM/PM, no imsak (derive as fajr-10)
- Some PDFs have Feb 29 in non-leap years (validated in parser)

### Diyanet (Turkey)
- Web scrape from https://namazvakitleri.diyanet.gov.tr
- Headless browser (Playwright) extracts WAF cookies, curl fetches yearly HTML tables
- 867 districts, times in 24h HH:MM, no imsak (derive as fajr-10)
- 23 duplicate district names resolved via shapeID mapping
- Official REST API exists (awqatsalah.diyanet.gov.tr) but requires paper registration and has harsh rate limits

## Future countries

### Official sources to investigate

| Country | Authority | Source | Notes |
|---------|-----------|--------|-------|
| Bangladesh | Islamic Foundation | [islamicfoundation.gov.bd](https://islamicfoundation.gov.bd) | Publishes district-level schedules, check if scrapeable |
| UAE | IACAD | [iacad.gov.ae](https://www.iacad.gov.ae/en/open-data/prayer-time-open-data) | Open data portal (link may be broken) |
| Morocco | Habous Ministry | [habous.gov.ma](https://habous.gov.ma) | Unofficial GitHub scraper exists |
