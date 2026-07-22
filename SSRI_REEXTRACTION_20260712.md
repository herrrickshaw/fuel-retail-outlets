# SSRI Re-Extraction — July 12, 2026

Re-ran the SSRI petrol-pump extraction and probed the wider SSRI/FuelABC API surface
(`/api/schema`, `/api/docs`) for other data types.

## Portal survey

SSRI's backend is a subscription platform ("FUELABC API Testing Platform", monetized via
RapidAPI). Beyond petrol pumps it exposes fuel-prices, fuel-prices-enroute, efficient-route,
mileage-economy, vehicle-makers/models/fuel-types/capacities, and co2-not-released — all
return `403 Authentication credentials were not provided` without a subscription key.

Only `/api/petrol-pumps/pumps/` is public. It now also has a public `statistics/` endpoint,
per-pump `price_history/`, and filters (`city`, `company`, `district`, `has_cng`,
`has_diesel`, `has_petrol`, `is_open_24_hours`). **No ATM/amenities field or endpoint exists
anywhere in the schema.**

## Re-extraction result

Full pagination via the official DRF `count`/`next`/`previous` cursor (page size capped at
100 regardless of `?limit=`), 1,074 pages, ~9.4 minutes.

| Metric | Jun 24, 2026 extraction | Jul 12, 2026 extraction | Change |
|---|---|---|---|
| Total pumps | 50,374 | 105,093 unique (API reported 107,380 live) | +108% |
| IOCL | 13,406 | 41,429 | +209% |
| BPCL | 16,979 | 25,803 | +52% |
| HPCL | 16,722 | 23,979 | +43% |
| Nayara | 101 | 9,061 | ×90 |
| Jio-bp | 841 | 1,244 | +48% |
| Reliance | 505 | 715 | +42% |
| Shell | 104 | 354 | +240% |

New fields captured: `petrol_price`, `diesel_price`, `cng_price`, `has_petrol`, `has_diesel`,
`has_cng`, `station_timing`, `district`, `direction_link`. 11,287 pumps have CNG; 35,218 are
24-hour stations.

**Data quality caveat (pagination drift):** the API reported 107,380 records at crawl start
but only 105,093 unique IDs were collected across all 1,074 pages (~2.1% gap, concentrated
in IOCL). This looks like the underlying table was being written to during the ~9-minute
crawl, shifting page windows on offset-based pagination.

## Deduplication (Jul 12, 2026, follow-up)

`id`-based dedup only catches API-level pagination drift. Checking the 105,093 records for
**content-level** duplicates (same `name` + `address` + `company` + `latitude`/`longitude`,
different `id`) found something bigger: **SSRI's own database contains genuinely duplicated
rows**, not just an extraction artifact. Six coordinates in Delhi alone each hold
2,600–3,986 byte-identical rows (same name, address, prices, and Google Maps CID) differing
only by `id` — e.g. "Irwin Road Service Station" at `(28.629249, 77.212676)` appears **3,986
times** with ids ranging 23,986–63,588.

| Metric | Count |
|---|---|
| Raw records fetched (unique by id) | 105,093 |
| Duplicate content-key groups (same name+address+company+coords) | 837 |
| Redundant rows removed | 22,484 (21.4%) |
| **Unique physical outlets after dedup** | **82,609** |

Dedup method: grouped by `(name, address, company, latitude, longitude)`; kept the
highest-`id` record per group as canonical (most recently inserted). Sample check of 837 dup
groups: 79% were fully identical on every field except `id`; the remaining 21% differed in a
minor field (price/timing), consistent with re-scraped snapshots rather than distinct
stations.

Post-dedup, the picture matches expectations far better: "Delhi" as a **state** value drops
from 22,080 (raw, mostly duplicate rows) to 421; IOCL drops from 41,429 to 19,446 (more than
half of the raw IOCL count was duplicate rows). Deduplicated total (82,609) sits at 79.9% of
PPAC's official May-2026 baseline of 103,450 total retail outlets (see
[PPAC_RETAIL_OUTLETS_MAY2026.md](PPAC_RETAIL_OUTLETS_MAY2026.md)) — a much more plausible
coverage ratio than the raw count, which had exceeded the PPAC baseline due to the
duplication.

## Files

- `api-data-integration/outlet_data_ssri_complete/ssri_all_pumps_20260712_095541.json` — raw fetch, 105,093 records (unique by id)
- `api-data-integration/outlet_data_ssri_complete/ssri_all_pumps_20260712_095541.csv`
- `api-data-integration/outlet_data_ssri_complete/ssri_all_pumps_summary_20260712_095541.json`
- `api-data-integration/outlet_data_ssri_complete/ssri_all_pumps_deduplicated_20260712.json` — deduplicated, 82,609 unique outlets
- `api-data-integration/outlet_data_ssri_complete/ssri_all_pumps_deduplicated_20260712.csv`
- `api-data-integration/outlet_data_ssri_complete/ssri_all_pumps_deduplicated_summary_20260712.json`
