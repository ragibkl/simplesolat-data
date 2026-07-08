# simplesolat-data

Centralized prayer times data for Malaysia, Singapore, Indonesia, Brunei, Sri Lanka, Turkey, UAE, Bosnia, and Albania.

Data is served via Netlify at:

```
https://simplesolat-data.netlify.app/
```

## Data available

### Countries

```
GET /countries.yaml
```

List of officially supported countries with geojson and mapping file URLs.

```yaml
countries:
  - code: MY
    name: Malaysia
    source: JAKIM
    geojson: https://simplesolat-data.netlify.app/geojson/MY-adm2-geojson-20260402.json
    mapping: https://simplesolat-data.netlify.app/mappings/MY-adm2-mapping-20260402.json
    shape_property: shapeName
```

The `shape_property` field tells consumers which geojson property to use as the mapping key (`shapeName` for most countries, `shapeID` for Turkey due to duplicate district names).

### Zones

```
GET /zones/{CC}.yaml
```

Per-country zone definitions. Each zone has a code, state, location, IANA timezone, and geojson shapes.

```yaml
zones:
  - code: SGR01
    country: MY
    state: Selangor
    location: Gombak, Petaling, Sepang, Hulu Langat, Hulu Selangor
    timezone: Asia/Kuala_Lumpur
    shapes:
      - Gombak
      - Hulu Langat
      - Hulu Selangor
      - Petaling
      - Sepang
```

Available files: `MY.yaml`, `SG.yaml`, `ID.yaml`, `BN.yaml`, `LK.yaml`, `TR.yaml`, `AE.yaml`, `BA.yaml`, `AL.yaml`

### Prayer times

```
GET /prayer-times/{CC}/{zone_code}/{year}-{month}.json
```

Monthly prayer times per zone. Times are local HH:MM in the zone's timezone.

```json
[
  {
    "date": "2026-01-01",
    "imsak": "05:56",
    "fajr": "06:06",
    "syuruk": "07:17",
    "dhuhr": "13:19",
    "asr": "16:42",
    "maghrib": "19:17",
    "isha": "20:31"
  },
  ...
]
```

Examples:
- `/prayer-times/MY/SGR01/2026-01.json` — Selangor, January 2026
- `/prayer-times/SG/SGP01/2026-04.json` — Singapore, April 2026
- `/prayer-times/ID/JKT01/2026-06.json` — Jakarta, June 2026
- `/prayer-times/BN/BRN01/2026-03.json` — Brunei-Muara, March 2026
- `/prayer-times/LK/LK01/2026-12.json` — Colombo, December 2026
- `/prayer-times/TR/TR9206/2026-01.json` — Ankara, January 2026
- `/prayer-times/AE/AE1/2026-01.json` — Abu Dhabi, January 2026

### GeoJSON

```
GET /geojson/{CC}-{adm}-geojson-{date}.json
```

Administrative boundary data for GPS-to-zone resolution. All from [geoBoundaries](https://www.geoboundaries.org/), unmodified.

### Mappings

```
GET /mappings/{CC}-{adm}-mapping-{date}.json
```

Maps geojson shape property to zone code and state. Derived from zone files via `scripts/generate_mappings.py`. Key is `shapeName` or `shapeID` depending on country's `shape_property`.

## How to use

### GPS to prayer times (mobile app flow)

1. Detect country from GPS using ADM0 geojson (bundled in app)
2. Fetch `/countries.yaml` (cache 1 month) — check if country is officially supported
3. If supported, fetch the country's geojson and mapping files (cache indefinitely by URL — new URL in countries.yaml = new data, delete old cached file)
4. Point-in-polygon lookup: GPS → `result.properties[shape_property]` → mapping → zone code
5. Fetch `/zones/{CC}.yaml` (cache 1 month) — get zone timezone
6. Fetch `/prayer-times/{CC}/{zone}/{year}-{month}.json` for current + next month
7. Convert local HH:MM to absolute time using the zone's IANA timezone for comparison with `Date.now()`

### Manual zone selection (web app flow)

1. Fetch `/countries.yaml` (cache 1 month) for country list
2. Fetch `/zones/{CC}.yaml` (cache 1 month) for zone list — use `state` for grouping, `location` for display
3. User selects zone
4. Fetch `/prayer-times/{CC}/{zone}/{year}-{month}.json` for current + next month

## Data sources

| Country | Source | Type | Update frequency |
|---------|--------|------|-----------------|
| MY | [JAKIM e-solat](https://www.e-solat.gov.my) | API | CI monthly (27th/28th) |
| SG | [data.gov.sg](https://data.gov.sg) | API | CI monthly (27th/28th) |
| ID | [EQuran.id](https://equran.id) | API | CI monthly (27th/28th) |
| BN | [KHEU Taqwim PDF](https://www.mora.gov.bn) | PDF | Manual, yearly |
| LK | [ACJU PDFs](https://www.acju.lk/prayer-times/) | PDF | Manual, yearly |
| TR | [Diyanet](https://namazvakitleri.diyanet.gov.tr) | Web scrape | Manual, yearly |
| AE | [AWQAF](https://www.awqaf.gov.ae) | API | CI monthly (27th/28th) |
| BA | [IZ BiH Vaktija](https://vaktija.ba) (via [vaktija.ba dataset](https://github.com/vaktija/vaktija.ba)) | Static dataset | Offline, regenerate yearly |
| AL | [KMSH](https://kmsh.al) (Diyanet data, via [namaz.kmsh.al](https://namaz.kmsh.al)) | Web scrape | Manual, yearly |

**Note on BA (Bosnia):** The authority is the **Islamic Community in Bosnia & Herzegovina (IZ BiH / Rijaset)**, which publishes the official Vaktija. Unlike the others, this Vaktija is a **perpetual** table — Sarajevo base times plus fixed per-city/month offsets that repeat every year (only DST varies) — so it's committed as a static dataset (`sources/vaktija/vaktija.json`) and regenerated offline per year via `scripts/fetch_vaktija.py`, with no runtime API. The data comes from the long-standing, canonical [vaktija.ba](https://vaktija.ba) (500k+ users), whose tabular structure matches the official IZ BiH takvim; we treat it as the authoritative source.

**Note on AL (Albania):** The authority is the **Muslim Community of Albania (KMSH)**, which publishes **Diyanet's** (Turkey, Presidency of Religious Affairs) prayer times for Albanian cities on its own site ([namaz.kmsh.al](https://namaz.kmsh.al)) — verified by an exact match to Diyanet's data. So Albania is fetched from Diyanet's international database using the **same scraper as Turkey** (`scripts/fetch_diyanet.py AL`), just with the 20 Albanian city IDs. Zone codes are `AL{diyanetId}`.

## Inclusion criteria

This repo only mirrors authorities that publish a **specific per-zone, per-day** prayer time table that mosques actually azan from. When the official body publishes only a calculation method, the [mobile app](https://github.com/ragibkl/simplesolat) falls back to client-side calculation via [adhan-js](https://github.com/batoulapps/adhan-js) — no entry needed here.

- ✅ Authority publishes specific times mosques call azan from (e.g., JAKIM's per-zone times — these differ from generic Karachi-method calc by several minutes due to per-zone empirical adjustments)
- ❌ Authority publishes only a calculation method (e.g., Umm Al-Qura, Karachi) — calc fallback handles this
- ❌ No authoritative central body exists — calc fallback handles this

### Investigated and excluded

**Saudi Arabia (SA)** — KACST publishes the **Umm Al-Qura method** (a calculation standard with Mecca-anchored sunset/moonset rules), not a queryable per-region time service. Every prayer time service for SA (Aladhan, IslamicFinder, etc.) computes locally using Umm Al-Qura. Mobile calc fallback uses `UmmAlQura` for SA.

**Bangladesh (BD)** — Islamic Foundation Bangladesh publishes an annual Ramadan PDF (per-district, 30 days, sehri/fajr/iftar only) and a printed "permanent prayer schedule" (Dhaka base + sehri/iftar offsets for 63 other districts, sample dates only — not daily). Neither is a queryable per-district full-prayer service. IF blesses the **University of Karachi method** (18°/18°); modern BD apps (Muslim Bangla, Ibadah, Muslim Pro) and republishers (kivabe.com, ihadis.com) all use Karachi-method GPS calculation. Mobile calc fallback should use `Karachi` for BD.

### Candidates being evaluated

| Country | Authority | Source | Notes |
|---------|-----------|--------|-------|
| Morocco | Habous Ministry | [habous.gov.ma](https://habous.gov.ma) | Unofficial GitHub scraper exists |

## Known data gaps

- Diyanet TR: Çukurova (Adana) and Akköy (Denizli) removed from Diyanet's district list — dropped from our zones; covered by central metro zones TR9146/TR9392
- Diyanet TR: 2 geoBoundaries shapes unmapped (Hamur, Merkez) — not in Diyanet district list
- AWQAF AE: only ADM1 geojson (7 emirates) — GPS resolves to emirate capital only. Investigate GADM ADM2 (192 districts) for finer resolution. Needs mapping 60 AWQAF areas to GADM neighborhoods.

## Caching recommendations

| Data | Cache duration | Invalidation |
|------|---------------|-------------|
| countries.yaml | 1 month | Refetch monthly |
| zones/{CC}.yaml | 1 month | Refetch monthly |
| GeoJSON / mappings | Indefinite | URL change in countries.yaml |
| Prayer times | Until month passes | Fetch current + next month |

## Contributing

To add a new country or fix data issues, see [docs/maintenance.md](docs/maintenance.md).

For how the data pipeline, mapping system, and zone resolution work, see [docs/architecture.md](docs/architecture.md).

## Setup

```bash
pip install -r requirements.txt
playwright install chromium  # needed for Turkey and UAE fetch scripts
```
