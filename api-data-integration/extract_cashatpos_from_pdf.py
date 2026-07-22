#!/usr/bin/env python3
"""
CASH@POS FUEL STATION EXTRACTION FROM PDF
==========================================
Extracts fuel station data from Cash@PoS and SBI Cash@PoS PDF documents.

Source PDFs:
1. Cash@PoS-UPDATED-19-11-16.pdf - Comprehensive retail outlet list (34 pages)
   Columns: SL, NAME, LOCATION, DISTRICT, STATE, BANK
2. sbicashatpos.pdf - SBI Cash@PoS fuel stations (9 pages)
   Columns: NAME, LOCATION, DISTRICT, STATE

Data includes:
- Fuel station name, location, district, state
- Banking partner (SBI)
- Cash@PoS/Mini ATM availability
- Geographic coordinates (to be geocoded)

Column extraction strategy (in order, per page):
1. pdfplumber's line-ruled table detection (works if the PDF draws grid lines)
2. pdfplumber's whitespace/text-based table detection (no ruling lines needed)
3. Word-position clustering fallback: bucket words into columns by x-position
   relative to the header row, for pages where neither table detector fires

Whichever strategy succeeds, columns are mapped to canonical field names by
matching header text (e.g. a header cell containing "NAME" -> name column),
not by a fixed column index, since column widths/order can vary by page/PDF.
"""

import pdfplumber
import pandas as pd
import json
from datetime import datetime
from pathlib import Path
import re
import argparse

# Canonical field -> header keywords that identify that column
HEADER_KEYWORDS = {
    'sl': ['SL', 'S.NO', 'SNO', 'SR'],
    'name': ['NAME OF RETAIL', 'NAME OF OUTLET', 'RETAIL OUTLET', 'DEALER NAME', 'NAME'],
    'location': ['LOCATION', 'ADDRESS', 'PLACE'],
    'district': ['DISTRICT'],
    'state': ['STATE'],
    'bank': ['BANK'],
}

INDIAN_STATES = [
    'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh', 'Goa',
    'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand', 'Karnataka', 'Kerala',
    'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland',
    'Odisha', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
    'Uttar Pradesh', 'Uttarakhand', 'West Bengal', 'Delhi', 'Chandigarh',
    'Jammu and Kashmir', 'Ladakh', 'Puducherry', 'Goa, Daman and Diu',
]
STATE_ALIASES = {'A.P.': 'Andhra Pradesh', 'AP': 'Andhra Pradesh', 'TS': 'Telangana'}


def _match_header(cell_text: str):
    """Return the canonical field name a header cell text refers to, or None."""
    if not cell_text:
        return None
    upper = cell_text.strip().upper()
    for field, keywords in HEADER_KEYWORDS.items():
        for kw in keywords:
            if kw in upper:
                return field
    return None


def _find_header_row(rows):
    """Scan the first few rows of a table for a row that looks like a header
    (matches at least 2 canonical fields). Returns (row_index, {field: col_index})."""
    for i, row in enumerate(rows[:5]):
        mapping = {}
        for col_idx, cell in enumerate(row):
            field = _match_header(cell or '')
            if field and field not in mapping:
                mapping[field] = col_idx
        if len(mapping) >= 2:
            return i, mapping
    return None, {}


def _resolve_state(text: str):
    if not text:
        return None
    for alias, canonical in STATE_ALIASES.items():
        if alias in text:
            return canonical
    for state in INDIAN_STATES:
        if state.upper() in text.upper():
            return state
    return None


class CashAtPosExtractor:
    """
    Extracts fuel station data from Cash@PoS PDF documents.

    PDFs contain lists of fuel stations with banking services (ATM/Cash@PoS).
    Useful for verifying banking infrastructure at fuel pumps.
    """

    def __init__(self):
        self.all_stations = {}
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.stats = {
            'pdf1_extracted': 0,
            'pdf2_extracted': 0,
            'total_unique': 0,
            'duplicates': 0,
            'unparsed_lines': 0,
        }

    # ------------------------------------------------------------------
    # Column extraction strategies
    # ------------------------------------------------------------------

    def _rows_via_tables(self, page):
        """Try pdfplumber's line-ruled and text-based table detectors."""
        for settings in (
            {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
            {"vertical_strategy": "text", "horizontal_strategy": "text"},
        ):
            try:
                tables = page.extract_tables(settings)
            except Exception:
                tables = []
            for table in tables:
                # a real data table has several rows and >=3 columns
                if len(table) >= 2 and max(len(r) for r in table) >= 3:
                    return table
        return None

    def _rows_via_word_clustering(self, page):
        """Fallback: bucket words into columns using the header row's x-positions.
        Works for whitespace-aligned pseudo-tables with no ruling lines."""
        words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
        if not words:
            return None

        # group words into lines by vertical (top) proximity
        lines = []
        current_line = []
        current_top = None
        for w in sorted(words, key=lambda w: (round(w['top'], 1), w['x0'])):
            if current_top is None or abs(w['top'] - current_top) <= 3:
                current_line.append(w)
                current_top = w['top'] if current_top is None else current_top
            else:
                lines.append(current_line)
                current_line = [w]
                current_top = w['top']
        if current_line:
            lines.append(current_line)

        # find the header line: first line whose joined text matches >=2 canonical fields
        header_line_idx = None
        col_bounds = None  # list of (field, x0) sorted by x0
        for i, line in enumerate(lines[:8]):
            joined = ' '.join(w['text'] for w in line)
            mapping = {}
            for w in line:
                field = _match_header(w['text'])
                if field and field not in mapping:
                    mapping[field] = w['x0']
            if len(mapping) >= 2:
                header_line_idx = i
                col_bounds = sorted(mapping.items(), key=lambda kv: kv[1])
                break

        if header_line_idx is None or not col_bounds:
            return None

        # build column ranges: each column spans from its header x0 to the next header's x0
        field_ranges = []
        for idx, (field, x0) in enumerate(col_bounds):
            next_x0 = col_bounds[idx + 1][1] if idx + 1 < len(col_bounds) else float('inf')
            field_ranges.append((field, x0 - 5, next_x0 - 5))  # small left margin tolerance

        rows = []
        for line in lines[header_line_idx + 1:]:
            row = {field: '' for field, _, _ in field_ranges}
            for w in line:
                for field, lo, hi in field_ranges:
                    if lo <= w['x0'] < hi:
                        row[field] = (row[field] + ' ' + w['text']).strip()
                        break
            if any(row.values()):
                rows.append(row)

        return {'_header_mapping_applied': True, 'rows': rows}

    def _extract_page_records(self, page, service_type: str, source_label: str, bank_default='SBI'):
        """Return a list of station dicts for one page, using the best available strategy."""
        records = []

        table = self._rows_via_tables(page)
        if table:
            header_idx, col_map = _find_header_row(table)
            if col_map and 'name' in col_map:
                for row in (table[header_idx + 1:] if header_idx is not None else table):
                    if len(row) <= max(col_map.values()):
                        continue
                    name = (row[col_map['name']] or '').strip() if col_map.get('name') is not None else ''
                    if not name or name.upper() in ('NAME', 'NIL', '-'):
                        continue
                    location = (row[col_map['location']] or '').strip() if 'location' in col_map else ''
                    district = (row[col_map['district']] or '').strip() if 'district' in col_map else ''
                    state_raw = (row[col_map['state']] or '').strip() if 'state' in col_map else ''
                    state = _resolve_state(state_raw) or _resolve_state(' '.join(str(c) for c in row if c))
                    bank = (row[col_map['bank']] or '').strip() if 'bank' in col_map else bank_default
                    if not state:
                        continue
                    records.append({
                        'name': name,
                        'location': location,
                        'district': district,
                        'state': state,
                        'bank': bank or bank_default,
                        'service_type': service_type,
                        'source': source_label,
                        'extraction_date': datetime.now().strftime('%Y-%m-%d'),
                    })
                if records:
                    return records
            # table detected but header/columns unrecognized - fall through to word clustering

        clustered = self._rows_via_word_clustering(page)
        if clustered:
            for row in clustered['rows']:
                name = row.get('name', '').strip()
                if not name or name.upper() in ('NAME', 'NIL', '-'):
                    continue
                state = _resolve_state(row.get('state', '')) or _resolve_state(' '.join(row.values()))
                if not state:
                    continue
                records.append({
                    'name': name,
                    'location': row.get('location', '').strip(),
                    'district': row.get('district', '').strip(),
                    'state': state,
                    'bank': row.get('bank', '').strip() or bank_default,
                    'service_type': service_type,
                    'source': source_label,
                    'extraction_date': datetime.now().strftime('%Y-%m-%d'),
                })

        return records

    # ------------------------------------------------------------------
    # Per-PDF entry points
    # ------------------------------------------------------------------

    def extract_from_pdf1(self, pdf_path: str, preview_only: bool = False, preview_n: int = 10):
        """Extract from Cash@PoS-UPDATED-19-11-16.pdf (SL, NAME, LOCATION, DISTRICT, STATE, BANK)."""
        print("📄 Extracting from Cash@PoS-UPDATED-19-11-16.pdf...")
        return self._run_extraction(pdf_path, service_type='Cash@PoS', source_label='Cash@PoS PDF',
                                     stat_key='pdf1_extracted', preview_only=preview_only, preview_n=preview_n)

    def extract_from_pdf2(self, pdf_path: str, preview_only: bool = False, preview_n: int = 10):
        """Extract from sbicashatpos.pdf (NAME, LOCATION, DISTRICT, STATE)."""
        print("\n📄 Extracting from sbicashatpos.pdf...")
        return self._run_extraction(pdf_path, service_type='Mini ATM / Cash@PoS', source_label='SBI Cash@PoS PDF',
                                     stat_key='pdf2_extracted', preview_only=preview_only, preview_n=preview_n)

    def _run_extraction(self, pdf_path, service_type, source_label, stat_key, preview_only, preview_n):
        stations = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                print(f"   Pages: {total_pages}")

                for page_num, page in enumerate(pdf.pages, 1):
                    page_records = self._extract_page_records(page, service_type, source_label)
                    stations.extend(page_records)

                    if preview_only and len(stations) >= preview_n:
                        print(f"\n   --- preview: first {preview_n} rows from page {page_num} ---")
                        for r in stations[:preview_n]:
                            print(f"   {r}")
                        return stations[:preview_n]

                    if page_num % 5 == 0:
                        print(f"   Processed {page_num}/{total_pages} pages... ({len(stations)} records so far)")

            if preview_only:
                print(f"\n   --- preview: {min(len(stations), preview_n)} rows (all {total_pages} page(s) scanned) ---")
                for r in stations[:preview_n]:
                    print(f"   {r}")
                return stations[:preview_n]

            print(f"  ✓ Extracted {len(stations)} records")
            self.stats[stat_key] = len(stations)
            return stations

        except Exception as e:
            print(f"  ✗ Error: {e}")
            return []

    def deduplicate_stations(self, stations: list):
        """Add stations with deduplication by name + district + state (falls back to name+state
        if district is blank, so pages without a district column still dedup sanely)."""
        for station in stations:
            district_part = station.get('district', '').upper()
            key = f"{station['name'].upper()}_{district_part}_{station['state'].upper()}"

            if key not in self.all_stations:
                self.all_stations[key] = station
            else:
                existing = self.all_stations[key]
                # prefer the record with more populated fields (location/district)
                if sum(bool(v) for v in station.values()) > sum(bool(v) for v in existing.values()):
                    self.all_stations[key] = station
                self.stats['duplicates'] += 1

        self.stats['total_unique'] = len(self.all_stations)

    def export_data(self, output_dir: str = "./outlet_data_cashatpos"):
        """Export extracted station data."""
        print("\n" + "=" * 80)
        print("\U0001F4BE EXPORTING CASH@POS STATION DATA")
        print("=" * 80)

        Path(output_dir).mkdir(exist_ok=True, parents=True)

        if not self.all_stations:
            print("✗ No data to export")
            return

        df = pd.DataFrame(list(self.all_stations.values()))

        print("\n  Exporting CSV...")
        csv_path = f"{output_dir}/cashatpos_fuel_stations_{self.timestamp}.csv"
        df.to_csv(csv_path, index=False)
        csv_size = Path(csv_path).stat().st_size / (1024 * 1024)
        print(f"    ✓ {csv_path} ({csv_size:.2f}MB, {len(df)} records)")

        print("  Exporting JSON...")
        json_path = f"{output_dir}/cashatpos_fuel_stations_{self.timestamp}.json"
        with open(json_path, 'w') as f:
            json.dump(list(self.all_stations.values()), f, indent=2)
        json_size = Path(json_path).stat().st_size / (1024 * 1024)
        print(f"    ✓ {json_path} ({json_size:.2f}MB)")

        print("  Generating summary...")
        summary = {
            'timestamp': self.timestamp,
            'total_stations': len(self.all_stations),
            'unique_states': len(set(s.get('state') for s in self.all_stations.values())),
            'stations_with_location': sum(1 for s in self.all_stations.values() if s.get('location')),
            'stations_with_district': sum(1 for s in self.all_stations.values() if s.get('district')),
            'extraction_stats': self.stats,
            'state_distribution': self._get_state_distribution(),
            'bank_distribution': self._get_bank_distribution(),
            'service_distribution': self._get_service_distribution(),
        }

        summary_path = f"{output_dir}/cashatpos_fuel_stations_summary_{self.timestamp}.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"    ✓ {summary_path}")

        print(f"\n✅ Export complete to {output_dir}/")
        return summary

    def _get_state_distribution(self):
        dist = {}
        for station in self.all_stations.values():
            state = station.get('state', 'Unknown')
            dist[state] = dist.get(state, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: x[1], reverse=True))

    def _get_bank_distribution(self):
        dist = {}
        for station in self.all_stations.values():
            bank = station.get('bank', 'Unknown')
            dist[bank] = dist.get(bank, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: x[1], reverse=True))

    def _get_service_distribution(self):
        dist = {}
        for station in self.all_stations.values():
            service = station.get('service_type', 'Unknown')
            dist[service] = dist.get(service, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: x[1], reverse=True))

    def print_summary(self, summary: dict):
        print("\n" + "=" * 80)
        print("\U0001F4CA CASH@POS STATION EXTRACTION SUMMARY")
        print("=" * 80)

        print("\n✅ EXTRACTION COMPLETE!")
        print(f"\n   Total Stations: {summary['total_stations']}")
        print(f"   Unique States: {summary['unique_states']}")
        print(f"   With location populated: {summary['stations_with_location']}")
        print(f"   With district populated: {summary['stations_with_district']}")

        print("\n   Extraction Statistics:")
        print(f"   • PDF1 (Cash@PoS): {summary['extraction_stats']['pdf1_extracted']}")
        print(f"   • PDF2 (SBI Cash@PoS): {summary['extraction_stats']['pdf2_extracted']}")
        print(f"   • Duplicates merged: {summary['extraction_stats']['duplicates']}")

        print("\n   State Distribution:")
        for state, count in list(summary['state_distribution'].items())[:10]:
            print(f"   • {state}: {count}")

        print("\n   Bank Distribution:")
        for bank, count in summary['bank_distribution'].items():
            print(f"   • {bank}: {count}")

        print("\n   Service Types:")
        for service, count in summary['service_distribution'].items():
            print(f"   • {service}: {count}")

    def run(self, pdf1_path: str, pdf2_path: str):
        """Run complete extraction."""
        print("\n" + "=" * 80)
        print("\U0001F680 CASH@POS FUEL STATION EXTRACTION FROM PDF")
        print("=" * 80)
        print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        stations1 = self.extract_from_pdf1(pdf1_path)
        self.deduplicate_stations(stations1)

        stations2 = self.extract_from_pdf2(pdf2_path)
        self.deduplicate_stations(stations2)

        summary = self.export_data()

        if summary:
            self.print_summary(summary)

        print(f"\nEnd: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80 + "\n")

    def preview(self, pdf1_path: str, pdf2_path: str, n: int = 10):
        """Print the first n parsed rows from each PDF without exporting anything,
        so column mapping can be sanity-checked before a full run."""
        print(f"\n--- PREVIEW MODE: first {n} rows per PDF, no export ---\n")
        self.extract_from_pdf1(pdf1_path, preview_only=True, preview_n=n)
        self.extract_from_pdf2(pdf2_path, preview_only=True, preview_n=n)


def main():
    parser = argparse.ArgumentParser(description="Extract Cash@PoS fuel station data from PDFs")
    parser.add_argument('--pdf1', default="/Users/umashankar/Downloads/Cash@PoS-UPDATED-19-11-16.pdf",
                         help="Path to Cash@PoS-UPDATED-19-11-16.pdf")
    parser.add_argument('--pdf2', default="/Users/umashankar/Downloads/sbicashatpos.pdf",
                         help="Path to sbicashatpos.pdf")
    parser.add_argument('--preview', action='store_true',
                         help="Print first N parsed rows per PDF and exit, without exporting")
    parser.add_argument('--preview-n', type=int, default=10, help="Rows to preview per PDF")
    args = parser.parse_args()

    extractor = CashAtPosExtractor()

    if args.preview:
        extractor.preview(args.pdf1, args.pdf2, n=args.preview_n)
    else:
        extractor.run(args.pdf1, args.pdf2)


if __name__ == "__main__":
    main()
