# PPAC Retail Outlets — Rural/Urban Split (as on 01.06.2026, Provisional)

Source: [Snapshot of India's Oil & Gas data — Monthly Ready Reckoner, May 2026](https://ppac.gov.in/)
(Petroleum Planning & Analysis Cell, Ministry of Petroleum & Natural Gas), Table 14
"Industry marketing infrastructure", user-supplied PDF
`1781699418_Snapshot_of_India_Oil_and_Gas_May2026_V1_A5.pdf`.

This is the official government count of retail outlets (petrol pumps) across all OMCs,
broken down by company and by rural vs. urban location — the authoritative counterpart to
the SSRI-scraped dataset in this repo.

## Retail outlets by company, rural vs. urban

| Company | Total ROs | Rural ROs | Urban ROs | Rural % |
|---|---:|---:|---:|---:|
| IOCL | 43,015 | 13,998 | 29,017 | 32.5% |
| BPCL | 25,405 | 6,778 | 18,627 | 26.7% |
| HPCL | 25,131 | 6,398 | 18,733 | 25.5% |
| RIL/RBML/RSIL | 2,221 | 130 | 2,091 | 5.9% |
| NEL (Nayara) | 7,056 | 2,160 | 4,896 | 30.6% |
| SHELL | 344 | 87 | 257 | 25.3% |
| MRPL & Others | 278 | 77 | 201 | 27.7% |
| **TOTAL** | **103,450** | **29,628** | **73,822** | **28.6%** |

**71.4% of India's 103,450 retail outlets are urban; 28.6% are rural.**

Notes:
- RIL/RBML/RSIL (Reliance Industries/Reliance BP Mobility/Reliance-Shell) has by far the
  lowest rural share (5.9%) — consistent with its urban/highway-corridor-focused rollout.
  IOCL and NEL (Nayara) have the highest rural shares (32.5%, 30.6%).
- Same table also reports (as on 01.06.2026): 313 POL terminals/depots, 312 aviation fuel
  stations, 25,608 LPG distributors, 214 LPG bottling plants, and alternate-fuel
  infrastructure at retail outlets — 7,643 CNG/LNG, 29,418 EV charging, 460 auto-LPG, 460
  compressed bio-gas, 81,475 solarized ROs.

## Cross-check vs SSRI-scraped data

| Source | Total outlets |
|---|---:|
| PPAC official (as on 01.06.2026) | 103,450 |
| SSRI raw fetch, Jul 12 2026 (unique by id) | 105,093 |
| SSRI deduplicated, Jul 12 2026 (unique by content-key) | 82,609 |

The deduplicated SSRI count (82,609) is 79.9% of the PPAC baseline — a plausible coverage
gap for a scraped dataset. The raw SSRI count (105,093) had exceeded PPAC's official total,
which was the tell that raw SSRI data contained substantial duplication (see
[SSRI_REEXTRACTION_20260712.md](SSRI_REEXTRACTION_20260712.md) for the dedup analysis).

PPAC does not publish coordinates or a rural/urban flag per individual outlet in this
report — only the aggregate company-level split above. SSRI's scraped records have no rural/
urban classification field either, so a per-outlet rural/urban join between the two sources
isn't possible from data currently in this repo.
