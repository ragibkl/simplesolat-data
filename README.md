# simplesolat-data

Centralized prayer times data for Malaysia, Singapore, Indonesia, Brunei, and Sri Lanka.

Data is served via GitHub Pages at:

```
https://ragibkl.github.io/simplesolat-data/
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
    geojson: data/geojson/MY-adm2-geojson-20260402.json
    mapping: data/mappings/MY-adm2-mapping-20260402.json
    shape_property: shapeName
```

### Zones

```
GET /zones/{CC}.yaml
```

Per-country zone definitions. Each zone has a code, state, location, IANA timezone, and geojson shape names.

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

Available files: `MY.yaml`, `SG.yaml`, `ID.yaml`, `BN.yaml`, `LK.yaml`

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

### GeoJSON

```
GET /geojson/{CC}-{adm}-geojson-{date}.json
```

Administrative boundary data for GPS-to-zone resolution. Each feature has a `shapeName` property.

### Mappings

```
GET /mappings/{CC}-{adm}-mapping-{date}.json
```

Maps geojson `shapeName` to zone code and state. Derived from zone files.

```json
{
  "Gombak": { "zone": "SGR01", "state": "Selangor" },
  "Petaling": { "zone": "SGR01", "state": "Selangor" },
  ...
}
```

## How to use

### GPS to prayer times (mobile app flow)

1. Detect country from GPS using ADM0 geojson (bundled in app)
2. Fetch `/countries.yaml` — check if country is officially supported
3. If supported, fetch the country's geojson and mapping files (cache indefinitely, URLs are datestamped — new URL = new data)
4. Point-in-polygon lookup: GPS → `shapeName` → mapping → zone code
5. Look up zone timezone from `/zones/{CC}.yaml`
6. Fetch `/prayer-times/{CC}/{zone}/{year}-{month}.json`
7. Convert local HH:MM to absolute time using the zone's IANA timezone for comparison with `Date.now()`

### Manual zone selection (web app flow)

1. Fetch `/countries.yaml` for country list
2. Fetch `/zones/{CC}.yaml` for zone list — use `state` for grouping, `location` for display
3. User selects zone
4. Fetch `/prayer-times/{CC}/{zone}/{year}-{month}.json`

### API sync flow

1. Read prayer time JSON files from this repo (GitHub raw or Pages)
2. Parse local HH:MM, convert to epoch using zone timezone
3. Store in database, serve to clients

## Time format

- All prayer times are **local HH:MM** in the zone's timezone
- Timezone is specified per zone in `zones/{CC}.yaml` as an IANA timezone (e.g. `Asia/Kuala_Lumpur`)
- To convert to absolute time, use the IANA timezone — this handles UTC offsets, DST, and political timezone changes automatically
- No seconds, no timezone info embedded in the time strings

## Zone codes

| Country | Prefix | Example | Source |
|---------|--------|---------|--------|
| MY | State abbreviation | JHR01, SGR01, WLY01 | JAKIM official codes |
| SG | SGP | SGP01 | Single zone |
| ID | Province abbreviation | ACH01, JKT01 | Generated convention |
| BN | BRN | BRN01-04 | Generated convention |
| LK | LK | LK01-13 | Generated convention |

## Data sources

| Country | Source | Type | Update frequency |
|---------|--------|------|-----------------|
| MY | [JAKIM e-solat](https://www.e-solat.gov.my) | API | CI monthly (27th/28th) |
| SG | [data.gov.sg](https://data.gov.sg) | API | CI monthly (27th/28th) |
| ID | [EQuran.id](https://equran.id) | API | CI monthly (27th/28th) |
| BN | [KHEU Taqwim PDF](https://www.mora.gov.bn) | PDF | Manual, yearly |
| LK | [ACJU PDFs](https://www.acju.lk/prayer-times/) | PDF | Manual, yearly |

## File naming conventions

- Prayer times: `{year}-{month}.json` (e.g. `2026-01.json`)
- GeoJSON: `{CC}-{adm_level}-geojson-{date}.json` (e.g. `MY-adm2-geojson-20260402.json`)
- Mappings: `{CC}-{adm_level}-mapping-{date}.json` (e.g. `MY-adm2-mapping-20260402.json`)
- Zones: `{CC}.yaml` (e.g. `MY.yaml`)

GeoJSON and mapping files are datestamped. When data is updated, a new file with a new date is committed and `countries.yaml` is updated to point to it. Consumers cache by URL — a new URL means new data.

## Caching recommendations

| Data | Cache duration | Invalidation |
|------|---------------|-------------|
| countries.yaml | 1 month | Refetch monthly |
| zones/{CC}.yaml | 1 month | Refetch monthly |
| GeoJSON / mappings | Indefinite | URL change in countries.yaml |
| Prayer times | Until month passes | Fetch current + next month |
