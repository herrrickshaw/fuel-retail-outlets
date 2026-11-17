# Fuel Retail Outlets — India

Extractors, normalised outlet datasets and two static web maps for petroleum retail outlets in India
(IOCL, BPCL, HPCL, Shell, Nayara), built from public OMC / retail-network feeds (SSRI, the BPCL
dealership locator, Cash@PoS PDFs) and PPAC reference counts. It also contains toll-plaza to outlet
distance and shortest-path analyses. Outputs are CSV/JSON/GeoJSON feeds, Excel summaries and HTML maps.

> Status: maintained research repo. Datasets are derived from public listings; treat as indicative
> for planning and visualisation, not an official registry. See `DATA_ACCESS.md`: the data files are on
> Git LFS, which is currently unreachable (budget exhausted) — clone with `GIT_LFS_SKIP_SMUDGE=1`.

> New here? See [How to use this repo with AI](HOW_TO_USE_WITH_AI.md).

## What it does
- Extracts SSRI petrol-pump records by state/district (`extract_all_ssri_complete.py`, `ssri_systematic_extractor.py`).
- Extracts BPCL dealerships (`extract_bpcl_dealership_data.py`, `extract_bpcl_by_zone_state_district.py`).
- Extracts Cash@PoS fuel stations from a PDF (`extract_cashatpos_from_pdf.py`).
- Unifies and de-duplicates sources (`integrate_multi_source_database.py`, `hybrid_aggregator.py`).
- Computes toll-plaza to outlet distances and Dijkstra shortest paths (`create_toll_retail_*`, `dijkstra_*`), sharing `geo.py`.
- Serves a locations map and a fuel-station gap-analysis heatmap as static pages.

## Quick start
```bash
git clone https://github.com/herrrickshaw/fuel-retail-outlets && cd fuel-retail-outlets
python3 -m venv .venv && source .venv/bin/activate
pip install pandas numpy requests openpyxl pytest
cd api-data-integration
python integrate_multi_source_database.py   # unify sources (needs the extracted feeds present)
```
Web apps: `cd fuel-pump-locations-map && python3 -m http.server 8000` and
`cd fuel-station-gap-analysis && python3 -m http.server 8001`.

## How it works
| Stage | Module(s) | Output |
|---|---|---|
| Extract SSRI | `extract_all_ssri_complete.py`, `ssri_petrol_pumps_api.py`, `ssri_html_scraper.py` | `outlet_data_ssri_*` |
| Extract BPCL / Cash@PoS | `extract_bpcl_*.py`, `extract_cashatpos_from_pdf.py` | `outlet_data_bpcl`, CSV |
| Integrate | `integrate_multi_source_database.py`, `hybrid_aggregator.py` | unified outlet feeds |
| Validate vs PPAC | `validate_*_against_*.py`, `generate_ppac_comparison_excel.py` | Excel comparison reports |
| Toll linkage | `integrate_toll_retail_database.py`, `create_toll_retail_*map.py`, `dijkstra_*.py` | Excel + HTML maps |

Great-circle distance is implemented once in `api-data-integration/geo.py`; the toll/Dijkstra scripts keep
their `haversine_distance` methods as thin delegates.

## Repository layout
| Path | Purpose |
|---|---|
| `api-data-integration/` | Extractors, integrators, analyses and generated feeds/reports |
| `fuel-pump-locations-map/` | Static locations map |
| `fuel-station-gap-analysis/` | Static gap-analysis heatmap |
| `data-sources/` | Source references |
| `tests/` | pytest characterisation tests (offline) |
| `SSRI_*.md`, `SSR_API_*.md` | API extraction guides and completeness reports |

## Data sources
| Source | What is taken | Access route | Caveat |
|---|---|---|---|
| SSRI (ssrinnovationlab API / site) | Petrol-pump records | API / HTML scraping | Scraped; may need auth, see `SSR_API_SETUP.md` |
| BPCL dealership locator | Dealer name, address, state | Public website | Scraped |
| Cash@PoS | Fuel stations with cash-at-POS | PDF | Extracted from PDF |
| PPAC | Statewise retail-outlet counts (baseline) | Excel | Reference only |

## Configuration
No environment variables. Several scripts contain absolute paths of the original author's machine
(`/Users/umashankar/...`); edit them or place inputs accordingly. API credentials, where needed, are
entered interactively (`ssr_api_handler.py`) and are never committed.

## Testing
```bash
pytest -q
```

## Limitations and known issues
- Git LFS data is currently unreachable (see `DATA_ACCESS.md`).
- Many scripts hard-code absolute local paths and are not runnable as-is on another machine.
- Extractors hit live sites and may break when those change; tests never do.
- Many BPCL records have no latitude/longitude.
- Lint is limited to syntax/undefined-name checks; a full ruff cleanup is pending.

## Related repositories
- [`toll-plaza-highways`](https://github.com/herrrickshaw/toll-plaza-highways) — toll plazas and toll-to-outlet distance analysis
- [`india-trade-export-analysis`](https://github.com/herrrickshaw/india-trade-export-analysis)
- [`global-market-scanners`](https://github.com/herrrickshaw/global-market-scanners) (separate domain)

## Licence
No licence file yet — all rights reserved.

## Suggestions: ATM access at fuel stations
Many fuel stations in Chennai have on-site ATMs, but not everywhere in India. Options include White Label
ATMs (e.g. India1, Indicash), merchants acting as Banking Correspondents with micro-ATMs, and fintech/OMC
store locators. See `ATM_OUTLET_JOIN_20260712.md`.
