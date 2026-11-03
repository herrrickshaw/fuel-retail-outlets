"""Characterisation tests for the pass-2 splits of the long export/map functions.

All input is synthetic. Golden values were captured from the code as it was before pass 2
(set RECORD_GOLDEN=1 to regenerate). Outputs compared: stdout, return value, and every file
written (text verbatim; xlsx as sheet cell values).
"""
import contextlib
import datetime as _dt
import io
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api-data-integration"))
GOLDEN = Path(__file__).parent / "golden" / "pass2_golden.json"
TS = "20260101_000000"


class _FixedDT(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 1, 1, 0, 0, 0)


def _snapshot(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root))
        if p.suffix == ".xlsx":
            import openpyxl
            wb = openpyxl.load_workbook(p)
            out[rel] = {ws.title: [list(map(repr, r)) for r in ws.iter_rows(values_only=True)] for ws in wb}
        else:
            out[rel] = p.read_text(encoding="utf-8")
    return out


def _run(tmp_path, monkeypatch, module, call):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "api-data-integration").mkdir(exist_ok=True)
    monkeypatch.setattr(module, "datetime", _FixedDT)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ret = call()
    return {"stdout": buf.getvalue().replace(str(tmp_path), "<TMP>"),
            "ret": repr(ret).replace(str(tmp_path), "<TMP>"),
            "files": _snapshot(tmp_path)}


def _check(name, result):
    if os.environ.get("RECORD_GOLDEN"):
        data = json.loads(GOLDEN.read_text()) if GOLDEN.exists() else {}
        data[name] = result
        GOLDEN.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False))
        return
    assert result == json.loads(GOLDEN.read_text())[name]


# ---- synthetic fixtures (no real dealer names or addresses) ----
TOLLS = [{"id": f"T{i}", "name": f"Plaza {i}", "highway": f"NH{i}", "state": "State A" if i % 2 else "State B",
          "lat": 20.0 + i, "lng": 75.0 + i} for i in range(3)]
OUTLETS = [{"id": f"O{i}", "name": f"Outlet {i}", "type": "Petrol Pump" if i % 2 else "ATM Station",
            "company": "Co X" if i % 2 else "Co Y", "state": "State A", "city": f"City {i}",
            "lat": 20.1 + i, "lng": 75.1 + i, "has_cng": bool(i % 2)} for i in range(4)]
DIST = [{"toll_id": t["id"], "toll_name": t["name"], "highway": t["highway"], "state": t["state"],
         "closest_outlets": [{"outlet_name": "Outlet 1", "company": "Co X", "distance": 3.5 + i,
                              "city": "City 1", "has_cng": True}] if i != 2 else [],
         "min_distance": 3.5 + i if i != 2 else None,
         "outlets_1km": i, "outlets_5km": i + 1, "outlets_10km": i + 2} for i, t in enumerate(TOLLS)]
PUMPS = [{"id": str(i), "name": f"Pump {i}", "latitude": 20.0 + i if i != 2 else 0, "longitude": 75.0 + i,
          "city": f"City {i % 2}", "state": f"State {i % 3}", "company": f"Co {i % 2}", "address": f"Addr {i}",
          "phone": f"000{i}", "petrol_price": 100.5 if i % 2 else None, "diesel_price": 90.0,
          "has_cng": bool(i % 2), "has_petrol": True, "has_diesel": i != 1, "station_timing": "24 hours"}
         for i in range(5)]


def test_toll_map_html(tmp_path, monkeypatch):
    import create_toll_retail_map as m
    g = m.TollRetailMapGenerator()
    g.timestamp = TS
    g.toll_plazas, g.retail_outlets = TOLLS, OUTLETS
    _check("toll_map", _run(tmp_path, monkeypatch, m, g.create_html_map))


def test_distance_map_html_and_excel(tmp_path, monkeypatch):
    import create_toll_retail_distance_map as m
    a = m.TollRetailDistanceAnalyzer()
    a.timestamp = TS
    a.toll_plazas, a.retail_outlets, a.distance_matrix = TOLLS, OUTLETS, DIST
    a.stats.update(toll_count=3, outlet_count=4, total_distances=12, outlets_within_1km=1,
                   outlets_within_5km=5, outlets_within_10km=9, outlets_within_25km=11, outlets_within_50km=12)
    _check("distance_map", _run(tmp_path, monkeypatch, m, a.create_html_map))
    _check("distance_excel", _run(tmp_path, monkeypatch, m, a.export_distance_excel))


def test_extract_all_ssri_pumps_export(tmp_path, monkeypatch):
    import extract_all_ssri_pumps as m
    e = m.CompleteSSRIExtractor()
    e.timestamp = TS
    e.all_pumps = {p["id"]: p for p in PUMPS}
    _check("pumps_export", _run(tmp_path, monkeypatch, m, lambda: e.export_all(str(tmp_path / "out"))))


def test_extract_all_ssri_pumps_export_empty(tmp_path, monkeypatch):
    import extract_all_ssri_pumps as m
    e = m.CompleteSSRIExtractor()
    _check("pumps_export_empty", _run(tmp_path, monkeypatch, m, lambda: e.export_all(str(tmp_path / "out"))))


def test_extract_all_ssri_complete_export(tmp_path, monkeypatch):
    import extract_all_ssri_complete as m
    e = m.CompleteSSRIExtractor()
    e.timestamp = TS
    e.all_pumps = {p["id"]: p for p in PUMPS}
    _check("complete_export", _run(tmp_path, monkeypatch, m, lambda: e.export_complete_database(str(tmp_path / "out"))))


def test_hybrid_export(tmp_path, monkeypatch):
    import hybrid_aggregator as m
    h = m.HybridOutletAggregator()
    h.stats.update(ppac=2, osm=2, google=1, duplicates_removed=1)
    h.deduped_outlets = [{"name": p["name"], "latitude": p["latitude"] or None, "longitude": p["longitude"],
                          "company": p["company"], "source": "ppac", "city": p["city"], "state": p["state"]}
                         for p in PUMPS]
    _check("hybrid_export", _run(tmp_path, monkeypatch, m, lambda: h.export_all_formats(str(tmp_path / "out"))))


def _service_analyzer(m):
    s = m.ServiceFilteredDijkstra()
    s.timestamp = TS
    s.toll_plazas = TOLLS
    s.service_outlets = [{"name": f"Svc {i}", "type": "Cash@PoS", "company": "SBI", "state": "State A",
                          "has_atm": True, "has_pos": i % 2 == 0, "has_cash": True, "source": "Cash@PoS"}
                         for i in range(3)]
    s.results = {t["id"]: {"min_service_distance": 4.256 + i, "service_outlets_reachable": i} for i, t in enumerate(TOLLS)}
    s.stats.update(total_outlets_available=10, service_outlets_filtered=3, filter_percentage=30.0,
                   dijkstra_runs=3, shortest_paths_found=3, avg_distance_to_service=4.756,
                   graph_vertices=6, graph_edges=9)
    return s


def test_service_export(tmp_path, monkeypatch):
    import dijkstra_filtered_service_outlets as m
    s = _service_analyzer(m)
    _check("service_export", _run(tmp_path, monkeypatch, m, s.export_service_analysis))


def test_service_load_and_filter(tmp_path, monkeypatch):
    import builtins
    import dijkstra_filtered_service_outlets as m
    import pandas as pd
    real_open = builtins.open
    ssri = [{"id": i, "name": f"Pump {i}", "company": "Co", "latitude": 20 + i, "longitude": 75 + i} for i in range(3)]
    ssri.append({"id": 9, "name": "NoCoords", "latitude": None, "longitude": None})

    def fake_open(path, *a, **k):
        if "ssri_all_pumps" in str(path):
            return io.StringIO(json.dumps(ssri))
        return real_open(path, *a, **k)

    df = pd.DataFrame([{"name": "Svc A", "service_type": "Cash@PoS", "latitude": 21.5, "longitude": 72.5, "state": "Gujarat"},
                       {"name": "Svc B", "service_type": "ATM", "latitude": None, "longitude": None, "state": "Gujarat"},
                       {"name": "Svc C", "service_type": "ATM", "latitude": None, "longitude": None, "state": "Nowhere"}])
    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(m.pd, "read_csv", lambda *a, **k: df)
    s = m.ServiceFilteredDijkstra()
    s.timestamp = TS

    def call():
        s.load_and_filter_service_outlets()
        return (s.stats, s.service_outlets, sorted(s.graph.vertices))

    _check("service_load", _run(tmp_path, monkeypatch, m, call))
