# ⛽ Fuel Retail Outlets — India

Petroleum **fuel retail outlet** data, extractors, and interactive maps for India —
covering IOCL, BPCL, HPCL, Shell and Nayara networks, sourced from public OMC /
petroleum-retail feeds (SSRI, BPCL dealership locator, CashAtPOS) and PPAC.

## Contents

| Path | What's in it |
|---|---|
| `api-data-integration/` | Extraction + integration pipeline: SSRI petrol-pump API scrapers, BPCL dealership extractors, CashAtPOS PDF extraction, multi-source aggregation, and the normalised `outlet_data_*` feeds (geojson/json/csv, state-wise) |
| `outlet_data_bpcl_complete/` | Full BPCL dealership dumps (geojson + summaries) |
| `fuel-pump-locations-map/` | Interactive web map of fuel pump / retail outlet locations |
| `fuel-station-gap-analysis/` | Fuel-station coverage **gap-analysis heatmap** dashboard |
| `data-sources/` | Source references — `RETAIL_OUTLETS_DATA_SOURCES.md`, quick-source list |
| `SSRI_*.md`, `SSR_API_*.md` | API extraction guides + completeness reports |

## Run the web apps
```bash
cd fuel-pump-locations-map && python3 -m http.server 8000   # locations map
cd fuel-station-gap-analysis && python3 -m http.server 8001 # gap-analysis heatmap
```

## Run the extractors
```bash
cd api-data-integration
python extract_all_ssri_complete.py        # SSRI petrol pumps (state/district)
python extract_bpcl_dealership_data.py     # BPCL dealerships
python integrate_multi_source_database.py  # unify sources
```

## Related repos
- [`toll-plaza-highways`](https://github.com/herrrickshaw/toll-plaza-highways) — toll-plaza & toll↔outlet distance analysis
- [`india-trade-export-analysis`](https://github.com/herrrickshaw/india-trade-export-analysis) — India trade/export analysis
- [`global-market-scanners`](https://github.com/herrrickshaw/global-market-scanners) — equity screeners (separate domain)

## Notes
Datasets are derived from public OMC retail-network listings; treat as indicative
for planning/visualisation, not an official registry.

# Suggestions
Many major fuel stations (petrol bunks) and convenience stores in Chennai feature on-site ATMs. However this is not the case in every part of the country, even rural India. These options provide 24/7 access to cash withdrawals and banking services. 
1. White Label ATMs: Independent operators (e.g., India1 ATM, Indicash) partner with local merchants in high-footfall areas like fuel stations to deploy full-service ATMs.
2. Merchant as a Banking Correspondent (BC): Small shop owners are equipped with handheld Micro ATMs by banks to act as mini-branches for the unbanked population.
3. Mobile & Virtual ATMs: Fintech solutions and major fuel marketers (like Bharat Petroleum's Umang initiatives) integrate digital wallets and nearby store locators to direct customers to cash points
