# ATM ↔ Retail Outlet Join — July 12, 2026

Attempted to join the SBI Cash@PoS ATM list (693 records,
`api-data-integration/outlet_data_cashatpos/`) against the deduplicated SSRI outlet catalog
(82,609 records) to attach an ATM flag to specific retail outlet IDs.

**Result: a reliable outlet-level join is not achievable with the currently extracted data.**
Only **18 of 693** ATM records (2.6%) can be confidently pinned to a specific SSRI outlet.
The rest are preserved, not discarded — see "What's maintained" below.

## Why the join mostly fails

The Cash@PoS CSV has no coordinates, address, or district (both fields are blank for all 693
rows) — only a `name` and `state`. That name field is unreliable for two different reasons
depending on source PDF:

- **218 records** (`service_type = Cash@PoS`, from `Cash@PoS-UPDATED-19-11-16.pdf`): the
  extractor (`extract_cashatpos_from_pdf.py`) captured the **serial-number column** as
  `name` (values are literally `"1000"`, `"1001"`, ... `"1217"`). There is no station name
  in this repo's copy of the data at all — unjoinable by any method.
- **475 records** (`service_type = Mini ATM / Cash@PoS`, from `sbicashatpos.pdf`): `name` is
  the **dealer/proprietor name**, not the station's registered name, and is column-truncated
  (e.g. `"CHINTAPALLI FILLING"` missing "STATION", `"A.G.K FILLNG"` missing a letter). SSRI's
  outlet names are the registered station name, which frequently differs from the dealer name
  printed on this list.

## Method

Fuzzy-matched each of the 475 named records against SSRI outlets **restricted to the same
state** (`difflib.SequenceMatcher` ratio on uppercased names), then tiered by score and
whether the best match was unique:

| Tier | Criteria | Count | % of 693 |
|---|---|---:|---:|
| **Confirmed** | score ≥ 0.95, unique best match | **18** | 2.6% |
| Ambiguous | score ≥ 0.95, tied with another equally-good candidate in-state | 15 | 2.2% |
| Low-confidence candidate | 0.85 ≤ score < 0.95 | 54 | 7.8% |
| Unmatched | score < 0.85 | 388 | 56.0% |
| Unmatchable | no usable name in source data | 218 | 31.5% |

Generic business words ("Petroleum", "Filling Station", "Automobiles", "Agencies") are
extremely common across ~5,000 candidates per state, so string similarity alone produces
false positives past ~0.85 — e.g. `"RAJANI PETROLEUM"` scores 0.938 against `"ANJANI
PETROLEUM"`, a different business. Manual spot-check of the 0.85–0.95 band confirmed this:
most are coincidental collisions, not real matches. Only the ≥0.95 + unique-match tier held
up under inspection.

## What's maintained

Nothing from the source ATM list is dropped — three files preserve the full picture:

- `atm_outlets_confirmed_join_20260712.{json,csv}` — the 18 confirmed outlet-level joins,
  with the matched SSRI `id`, name, company, address, district, and coordinates attached.
  Labeled `confirmed_high_similarity_unique`; still not field-verified, just the strongest
  defensible candidates from available data.
- `atm_outlets_unresolved_20260712.{json,csv}` — all 675 remaining ATM records (ambiguous,
  low-confidence, unmatched, and unmatchable), each tagged with its `resolution_status` and,
  where one exists, its best candidate SSRI id/name/score for manual review.
- `atm_join_summary_20260712.json` — the tier counts above plus method/caveat notes.

## To actually fix this

A trustworthy join needs the source PDFs re-extracted with the district/location columns
correctly captured (the current extractor drops them entirely) and the serial-number-as-name
bug in `extract_cashatpos_from_pdf.py` fixed. Neither source PDF
(`Cash@PoS-UPDATED-19-11-16.pdf`, `sbicashatpos.pdf`) is present in this repo, so that
re-extraction is out of scope here — if you can supply those PDFs, the extractor can be
fixed to pull `district`, and the join re-run with district as an additional match key,
which should raise the confirmed-match rate substantially.
