# TODO

See [README.md](README.md) for data format, usage flows, and API reference.
See [docs/architecture.md](docs/architecture.md) and [docs/maintenance.md](docs/maintenance.md) for technical details.

## Open issues

- [ ] Diyanet TR: 2 districts under maintenance (TR17876/Çukurova, TR17898/Akköy) — retry when Diyanet fixes
- [ ] Diyanet TR: 2 geoBoundaries shapes unmapped (Hamur, Merkez) — not in Diyanet district list
- [ ] AWQAF AE: Jul-Dec 2026 not yet published — re-run fetch_awqaf.py when available
- [ ] AWQAF AE: only ADM1 geojson (7 emirates) — GPS resolves to emirate capital only. Investigate GADM ADM2 (192 districts) for finer resolution. Needs mapping 60 AWQAF areas to GADM neighborhoods.
- [ ] JAKIM MY: upstream data error SBH08 2026-04-03 imsak was 15:20 — fixed manually, report to JAKIM

## Future countries

| Country | Authority | Source | Notes |
|---------|-----------|--------|-------|
| Bangladesh | Islamic Foundation | [islamicfoundation.gov.bd](https://islamicfoundation.gov.bd) | Publishes district-level schedules, check if scrapeable |
| Morocco | Habous Ministry | [habous.gov.ma](https://habous.gov.ma) | Unofficial GitHub scraper exists |
