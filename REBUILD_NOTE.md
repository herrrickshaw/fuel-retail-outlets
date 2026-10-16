# LFS-free rebuild — 2026-07-23

This repo was rebuilt without Git LFS (account LFS budget exhausted; the old
repo's ~236 MB of LFS data dumps had become unreadable behind the budget block).

What changed:
- **SSRI pump dumps (June 24 / July 12 snapshots, ~230 MB)** — removed.
  Superseded by the fresh canonical crawl included here:
  `api-data-integration/outlet_data_ssri_complete/ssri_pumps_raw_20261016.jsonl.gz`
  (104,945 unique pumps, crawled 2026-10-16 from the public SSRI API).
  Re-crawl any time with `api-data-integration/crawl_ssri.py` (~6 min).
- **Derived files** (unified DB, dedup CSVs, map `locations-data.js`) — removed;
  re-derivable from the raw crawl via the scripts in `api-data-integration/`.
- **Small join outputs** (CashAtPOS, BPCL, ATM joins, <1 MB total) — removed;
  re-derivable via the extractor scripts (`extract_bpcl_regional_dealerships.py`
  and the join scripts referenced in the docs).

Full history of the old repo (code + docs + LFS pointer records) is bundled at
`~/repos/branch-archives/fuel-retail-outlets_full_pre-rebuild_2026-07-23.bundle`
and replicated to Dropbox/GDrive by the nightly backup.

Data policy going forward: data files live in regular git (no LFS), each under
100 MB, with the raw crawl as the single canonical artifact and everything else
derived by script.

## Update — 2026-10-16
Re-crawled SSRI: API reports 107,380 rows; 104,945 unique ids, 0 failed pages.
Versus the 2026-07-22 snapshot: 1,300 ids added, 1,390 removed (net -90).
