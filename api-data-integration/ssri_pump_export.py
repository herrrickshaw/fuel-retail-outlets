"""Export helpers for the SSRI pump extractor (CSV / JS / GeoJSON / JSON / summary writers).

Mixed into CompleteSSRIExtractor; expects `self.timestamp` and `self.stats`.
"""
import json
from pathlib import Path

import pandas as pd


class PumpExportMixin:
    """File writers for the deduplicated pump list."""

    def _export_csv(self, pumps_list, output_dir):
        """Write the pump records as CSV (one row per pump)."""
        print(f"\n  Exporting CSV...")
        df = pd.DataFrame(pumps_list)
        csv_path = f"{output_dir}/ssri_all_pumps_{self.timestamp}.csv"
        df.to_csv(csv_path, index=False)
        csv_size = Path(csv_path).stat().st_size / (1024*1024)
        print(f"    ✓ {csv_path} ({csv_size:.2f}MB)")

    def _export_js(self, pumps_list, output_dir, generated):
        """Write the pump records as a JavaScript data file (FUEL_PUMP_LOCATIONS + OUTLET_STATS)."""
        print(f"  Exporting JavaScript...")
        js_path = f"{output_dir}/ssri_all_pumps_{self.timestamp}.js"
        with open(js_path, 'w') as f:
            f.write(f"// SSRI Complete Petrol Pumps Database\n")
            f.write(f"// Generated: {generated}\n")
            f.write(f"// Total pumps: {len(pumps_list)}\n\n")
            f.write(f"const FUEL_PUMP_LOCATIONS = {json.dumps(pumps_list)};\n\n")
            f.write(f"const OUTLET_STATS = {{\n")
            f.write(f"  total: {len(pumps_list)},\n")
            f.write(f"  states: {len(set(p['state'] for p in pumps_list))},\n")
            f.write(f"  cities: {len(set(p['city'] for p in pumps_list))},\n")
            f.write(f"  companies: {len(set(p['company'] for p in pumps_list))},\n")
            f.write(f"  source: 'SSRI Petrol Pumps API (Complete)'\n")
            f.write(f"}};\n")
        js_size = Path(js_path).stat().st_size / (1024*1024)
        print(f"    ✓ {js_path} ({js_size:.2f}MB)")

    @staticmethod
    def _pump_feature(pump):
        """GeoJSON Point feature for one pump (longitude, latitude order)."""
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [pump['longitude'], pump['latitude']]
            },
            "properties": {
                "name": pump['name'],
                "company": pump['company'],
                "city": pump['city'],
                "state": pump['state'],
                "address": pump.get('address', '')
            }
        }

    def _export_geojson(self, pumps_list, output_dir):
        """Write a GeoJSON FeatureCollection of the pumps that have coordinates."""
        print(f"  Exporting GeoJSON...")
        geojson = {"type": "FeatureCollection", "features": []}
        for pump in pumps_list:
            if pump['latitude'] and pump['longitude']:
                geojson["features"].append(self._pump_feature(pump))

        geojson_path = f"{output_dir}/ssri_all_pumps_{self.timestamp}.geojson"
        with open(geojson_path, 'w') as f:
            json.dump(geojson, f)
        geojson_size = Path(geojson_path).stat().st_size / (1024*1024)
        print(f"    ✓ {geojson_path} ({geojson_size:.2f}MB, {len(geojson['features'])} features)")

    def _export_json(self, pumps_list, output_dir):
        """Write the pump records as indented JSON."""
        print(f"  Exporting JSON...")
        json_path = f"{output_dir}/ssri_all_pumps_{self.timestamp}.json"
        with open(json_path, 'w') as f:
            json.dump(pumps_list, f, indent=2)
        json_size = Path(json_path).stat().st_size / (1024*1024)
        print(f"    ✓ {json_path} ({json_size:.2f}MB)")

    @staticmethod
    def _count_by(pumps_list, key):
        """Count pumps per value of `key`."""
        counts = {}
        for pump in pumps_list:
            counts[pump[key]] = counts.get(pump[key], 0) + 1
        return counts

    def _build_summary(self, pumps_list):
        """State/company breakdown plus extraction statistics."""
        state_counts = self._count_by(pumps_list, 'state')
        city_counts = self._count_by(pumps_list, 'city')
        company_counts = self._count_by(pumps_list, 'company')
        return {
            'timestamp': self.timestamp,
            'total_pumps': len(pumps_list),
            'unique_states': len(state_counts),
            'unique_cities': len(city_counts),
            'unique_companies': len(company_counts),
            'states': dict(sorted(state_counts.items(), key=lambda x: x[1], reverse=True)),
            'companies': dict(sorted(company_counts.items(), key=lambda x: x[1], reverse=True)),
            'extraction_stats': self.stats
        }

    def _export_summary(self, pumps_list, output_dir):
        """Write the summary JSON and return the summary dict."""
        print(f"  Generating summary...")
        summary = self._build_summary(pumps_list)
        summary_path = f"{output_dir}/ssri_all_pumps_summary_{self.timestamp}.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"    ✓ {summary_path}")
        return summary
