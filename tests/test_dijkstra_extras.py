"""Remaining behaviour of the two Dijkstra analyses: path details, graph construction from
fake inputs, the service-outlet loaders and the Excel exports."""
import json

import pandas as pd
import pytest

import dijkstra_filtered_service_outlets as fs
import dijkstra_toll_retail_shortest_path as ts

KM = 1 / 111.195


@pytest.fixture
def cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "api-data-integration").mkdir()
    return tmp_path


def line_graph():
    g = ts.DijkstraGraph()
    g.add_vertex("T", "toll_plaza", 10.0, 20.0)
    g.add_vertex("O1", "petrol_pump", 10.0 + 1 * KM, 20.0)
    g.add_vertex("O2", "petrol_pump", 10.0 + 3 * KM, 20.0)
    g.add_edge("T", "O1", 1.0)
    g.add_edge("O1", "O2", 2.0)
    return g


# ------------------------------------------------------------------ DijkstraShortestPath details
def test_graph_edges_are_directed_and_vertices_registered():
    g = line_graph()
    assert g.edges["T"] == [("O1", 1.0)] and g.edges["O1"] == [("O2", 2.0)]      # u -> v only
    assert g.vertices["T"]["type"] == "toll_plaza" and g.vertices["O2"]["lat"] == pytest.approx(10.0 + 3 * KM)


def test_path_details_total_hops_and_unreachable():
    sp = ts.DijkstraShortestPath(line_graph())
    sp.find_shortest_paths_from_tolls(["T"])
    d = sp.get_shortest_path_details("T", "O2")
    assert d["path"] == ["T", "O1", "O2"] and d["hops"] == 2 and d["total_distance"] == 3.0
    assert d["hop_distances"] == pytest.approx([1.0, 2.0], abs=0.01)
    assert sp.get_shortest_path_details("T", "T")["hops"] == 0
    assert sp.get_shortest_path_details("nope", "O2") == {} and sp.reconstruct_path("nope", "O2") == []
    sp.graph.add_vertex("Z", "petrol_pump", 0, 0)
    sp.find_shortest_paths_from_tolls(["T"])
    assert sp.get_shortest_path_details("T", "Z") == {}                      # island: no path


def test_find_shortest_paths_stats_and_missing_results():
    sp = ts.DijkstraShortestPath(line_graph())
    sp.find_shortest_paths_from_tolls(["T"])
    assert sp.results["T"]["min_distance"] == 1.0 and sp.results["T"]["visited"] == 2
    assert sp.stats["dijkstra_runs"] == 1 and sp.stats["shortest_paths_found"] == 2
    assert sp.stats["avg_distance"] == pytest.approx(2.0) and sp.stats["total_distance"] == 4.0
    lone = ts.DijkstraGraph()
    lone.add_vertex("T", "toll_plaza", 0, 0)
    sp2 = ts.DijkstraShortestPath(lone)
    sp2.find_shortest_paths_from_tolls(["T"])
    assert sp2.results["T"]["min_distance"] == float("inf") and sp2.results["T"]["visited"] == 0
    assert sp2.stats["shortest_paths_found"] == 0


# ------------------------------------------------------------------ TollRetailShortestPathAnalyzer
@pytest.fixture
def tsa(monkeypatch, tmp_path, cwd):
    toll_df = pd.DataFrame({"plaza_name": ["A Toll Plaza", "B Toll Plaza", "C Toll Plaza", " "],
                            "state": ["Goa", "Goa", "Goa", "Goa"], "latitude": [15.0, 15.0 + 20 * KM, 15.0 + 200 * KM, 1.0],
                            "longitude": [74.0, 74.0, 74.0, 1.0]})
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: toll_df.copy())
    ssri = tmp_path / "ssri.json"
    ssri.write_text(json.dumps([{"id": 1, "name": "P1", "latitude": 15.0 + 1 * KM, "longitude": 74.0},
                                {"id": 2, "name": "P2", "latitude": None, "longitude": 74.0}]))
    real_open = open
    monkeypatch.setattr(ts, "open", lambda path, *a, **k: real_open(ssri, *a, **k), raising=False)
    return ts.TollRetailShortestPathAnalyzer()


def test_build_graph_edges_and_nearby_toll_links(tsa):
    tsa.build_graph()
    assert [t["id"] for t in tsa.toll_plazas] == ["TOLL_0", "TOLL_1", "TOLL_2"]       # blank plaza_name dropped
    assert [o["id"] for o in tsa.retail_outlets] == ["OUTLET_1"]                      # outlet without latitude dropped
    g = tsa.graph
    assert any(n == "OUTLET_1" for n, _ in g.edges["TOLL_0"])
    assert any(n == "TOLL_1" for n, _ in g.edges["TOLL_0"])                           # 20 km < 50 km: linked
    assert not any(n == "TOLL_2" for n, _ in g.edges["TOLL_0"])                       # 200 km: not linked


def test_analysis_export_and_run(tsa, cwd, capsys):
    tsa.run()
    files = list((cwd / "api-data-integration").glob("DIJKSTRA_SHORTEST_PATHS_*.xlsx"))
    assert len(files) == 1
    xl = pd.ExcelFile(files[0])
    assert xl.sheet_names == ["SUMMARY", "TOLL SHORTEST PATHS", "ALGORITHM DETAILS"]
    paths = pd.read_excel(files[0], sheet_name="TOLL SHORTEST PATHS")
    assert list(paths["Toll Plaza"]) == ["A Toll Plaza", "B Toll Plaza", "C Toll Plaza"]
    summ = dict(zip(*[pd.read_excel(files[0], sheet_name="SUMMARY")[c] for c in ("Metric", "Value")]))
    assert summ["Toll Plazas"] == 3 and summ["Retail Outlets"] == 1
    assert tsa.dijkstra.results["TOLL_0"]["min_distance"] == pytest.approx(1.0, abs=0.01)


def test_ts_main(monkeypatch):
    seen = {}
    monkeypatch.setattr(ts.TollRetailShortestPathAnalyzer, "run", lambda self: seen.setdefault("ran", True))
    ts.main()
    assert seen == {"ran": True}


# ------------------------------------------------------------------ ServiceFilteredDijkstra
@pytest.fixture
def sfd():
    return fs.ServiceFilteredDijkstra()


def test_cashatpos_coords_fallback_rules():
    c = fs.ServiceFilteredDijkstra._cashatpos_coords
    assert c({"latitude": 1.5, "longitude": 2.5}) == (1.5, 2.5)
    assert c({"latitude": float("nan"), "longitude": 2.5, "state": " Gujarat "}) == (22.5, 72.5)
    assert c({"latitude": None, "longitude": None, "state": "Atlantis"}) is None
    assert c({"state": "Karnataka"} | {"latitude": float("nan"), "longitude": float("nan")}) == (15.0, 76.0)


def test_load_ssri_pumps_caps_at_2000_and_skips_blank_coordinates(sfd, monkeypatch, tmp_path):
    data = [{"id": i, "name": f"p{i}", "latitude": 10.0, "longitude": 20.0} for i in range(2500)]
    data[3]["latitude"] = None
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data))
    real_open = open
    monkeypatch.setattr(fs, "open", lambda path, *a, **k: real_open(p, *a, **k), raising=False)
    out = []
    sfd._load_ssri_pumps(out)
    assert len(out) == 1999 and out[0]["id"] == "OUTLET_SSRI_0" and out[0]["has_atm"] is False
    monkeypatch.setattr(fs, "open", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("x")), raising=False)
    sfd._load_ssri_pumps(out)                                                  # failure is reported, not raised
    assert len(out) == 1999


def test_load_cashatpos_outlets_and_filter_pipeline(sfd, monkeypatch, tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps([{"id": 1, "name": "pump", "latitude": 10.0, "longitude": 20.0, "company": "IOCL"}]))
    real_open = open
    monkeypatch.setattr(fs, "open", lambda path, *a, **k: real_open(p, *a, **k), raising=False)
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: pd.DataFrame({
        "name": ["A", "B", "C"], "state": ["Gujarat", "Atlantis", "Goa"], "service_type": ["ATM", "ATM", None],
        "latitude": [None, None, 15.0], "longitude": [None, None, 74.0]}))
    sfd.load_and_filter_service_outlets()
    assert [o["id"] for o in sfd.service_outlets] == ["OUTLET_CASHATPOS_0", "OUTLET_CASHATPOS_2"]    # Atlantis dropped
    assert (sfd.service_outlets[0]["lat"], sfd.service_outlets[0]["lng"]) == (22.5, 72.5)
    assert sfd.service_outlets[0]["type"] == "ATM" and sfd.service_outlets[1]["has_pos"] is True
    assert sfd.stats["total_outlets_available"] == 3 and sfd.stats["service_outlets_filtered"] == 2
    assert sfd.stats["filter_percentage"] == pytest.approx(2 / 3 * 100)
    assert sfd.stats["graph_vertices"] == 2 and set(sfd.graph.vertices) == {"OUTLET_CASHATPOS_0", "OUTLET_CASHATPOS_2"}
    assert sfd.graph.vertices["OUTLET_CASHATPOS_0"]["services"]["bank_partner"] == "State Bank of India"


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="a blank service_type cell is NaN and str(NaN) == 'nan', so the 'Cash@PoS' default in "
                          "row.get('service_type', 'Cash@PoS') is never used for CSV input")
def test_blank_service_type_gets_the_documented_default(sfd, monkeypatch):
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: pd.DataFrame({
        "name": ["A"], "state": ["Goa"], "service_type": [None], "latitude": [15.0], "longitude": [74.0]}))
    out = []
    sfd._load_cashatpos_outlets(out)
    assert out[0]["type"] == "Cash@PoS"


def test_load_cashatpos_failure_and_zero_total(sfd, monkeypatch):
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("x")))
    out = []
    sfd._load_cashatpos_outlets(out)
    assert out == [] and sfd.service_outlets == []
    sfd._update_filter_stats([])
    assert sfd.stats["filter_percentage"] == 0                                    # no division by zero


def make_ready(sfd, n_toll=1, n_out=3):
    for i in range(n_toll):
        sfd.graph.add_vertex(f"T{i}", "toll_plaza", 10.0 + i, 20.0)
        sfd.toll_plazas.append({"id": f"T{i}", "name": f"Toll{i}", "state": "Goa", "lat": 10.0 + i, "lng": 20.0})
    for j in range(n_out):
        o = {"id": f"S{j}", "name": f"Out{j}", "type": "ATM", "company": "SBI", "lat": 10.0 + (j + 1) * 0.1, "lng": 20.0,
             "has_atm": True, "has_pos": True, "has_cash": True, "bank_partner": "State Bank of India", "source": "Cash@PoS"}
        sfd.service_outlets.append(o)
    sfd._add_service_vertices()
    sfd.build_service_edges()


def test_build_edges_and_dijkstra_over_service_graph(sfd):
    make_ready(sfd, n_toll=2, n_out=3)
    assert sfd.stats["graph_edges"] == 6
    d, pred = sfd.dijkstra_service_paths("T0")
    assert d["T0"] == 0 and d["S0"] == pytest.approx(11.12, abs=0.05) and pred["S0"] == "T0"
    assert d["S2"] > d["S1"] > d["S0"]
    assert d["T1"] == float("inf")                                                # tolls are only linked to outlets, never to each other


def test_find_paths_caps_at_100_tolls_and_records_stats(sfd):
    make_ready(sfd, n_toll=101, n_out=2)
    sfd.find_shortest_service_paths()
    assert sfd.stats["dijkstra_runs"] == 100 and len(sfd.results) == 100 and "T100" not in sfd.results
    assert sfd.results["T0"]["service_outlets_reachable"] == 2
    assert sfd.stats["avg_distance_to_service"] == pytest.approx(
        sum(r["min_service_distance"] for r in sfd.results.values()) / 100)


def test_export_service_analysis_sheets(sfd, cwd, capsys):
    make_ready(sfd, n_toll=2, n_out=2)
    sfd._update_filter_stats(list(sfd.service_outlets))
    sfd.find_shortest_service_paths()
    path = sfd.export_service_analysis()
    assert pd.ExcelFile(path).sheet_names == ["SUMMARY", "TOLL TO SERVICE OUTLETS", "SERVICE OUTLET DIRECTORY", "FILTER ANALYSIS"]
    toll = pd.read_excel(path, sheet_name="TOLL TO SERVICE OUTLETS")
    assert list(toll["Toll Plaza"]) == ["Toll0", "Toll1"] and toll.loc[0, "Service Outlets Reachable"] == 2
    d = pd.read_excel(path, sheet_name="SERVICE OUTLET DIRECTORY", keep_default_na=False)
    assert list(d["Has ATM"]) == ["✓", "✓"] and d.loc[0, "State"] == "N/A"
    f = pd.read_excel(path, sheet_name="FILTER ANALYSIS")
    assert f.loc[0, "Status"] == "✓ 2 outlets"
    sfd.print_summary()


def test_fs_run_and_main(monkeypatch, cwd):
    toll_df = pd.DataFrame({"plaza_name": ["T1", "T2"], "state": ["Goa", "Goa"], "latitude": [15.0, None], "longitude": [74.0, None]})
    cash_df = pd.DataFrame({"name": ["A"], "state": ["Goa"], "service_type": ["ATM"], "latitude": [15.1], "longitude": [74.0]})
    frames = iter([toll_df, cash_df])
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: next(frames))
    monkeypatch.setattr(fs, "open", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("x")), raising=False)
    fs.main()
    assert list((cwd / "api-data-integration").glob("DIJKSTRA_SERVICE_OUTLETS_*.xlsx"))
