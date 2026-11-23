"""create_toll_retail_map and the loader/export/HTML half of create_toll_retail_distance_map.
Inputs are injected or written to tmp_path; absolute /Users/... paths are made unreachable."""
import json

import pandas as pd
import pytest

import create_toll_retail_distance_map as dm
import create_toll_retail_map as tm

KM = 1 / 111.195


@pytest.fixture
def blocked(monkeypatch, tmp_path):
    """Any open()/read_csv() of an absolute /Users path fails; relative writes go to tmp_path."""
    real_open = open

    def guarded(path, *a, **k):
        if str(path).startswith("/Users/"):
            raise FileNotFoundError(path)
        return real_open(path, *a, **k)

    for m in (tm, dm):
        monkeypatch.setattr(m, "open", guarded, raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "api-data-integration").mkdir()
    return real_open


# ------------------------------------------------------------------ create_toll_retail_map
@pytest.fixture
def gen():
    g = tm.TollRetailMapGenerator()
    g.toll_plazas = [{"name": "P", "highway": "NH1", "state": "Goa", "lat": 15.0, "lng": 74.0}]
    g.retail_outlets = [
        {"name": "Pump", "type": "Petrol Pump", "company": "IOCL", "state": "Goa", "city": "x", "lat": 15.1, "lng": 74.1, "has_cng": False},
        {"name": "ATM", "type": "Cash@PoS ATM", "company": "SBI", "state": "Goa", "city": "x", "lat": 15.2, "lng": 74.2, "has_cng": False},
        {"name": "NoGPS", "type": "Cash@PoS ATM", "company": "SBI", "state": "Goa", "city": "x", "lat": None, "lng": None, "has_cng": False},
    ]
    return g


def test_geojson_features(gen):
    feats = gen.create_geojson_features()
    assert [f["properties"]["name"] for f in feats] == ["P", "Pump", "ATM"]          # outlet without coordinates dropped
    assert feats[0]["geometry"]["coordinates"] == [74.0, 15.0] and feats[0]["properties"]["color"] == "blue"
    assert (feats[1]["properties"]["color"], feats[2]["properties"]["color"]) == ("green", "orange")
    assert feats[1]["properties"]["icon"] == "⛽" and feats[2]["properties"]["icon"] == "🏧"
    gen.toll_plazas = []
    assert len(gen.create_geojson_features()) == 2


def test_html_map_counts_and_file(gen, blocked, tmp_path):
    out = gen.create_html_map()
    assert out.startswith("./api-data-integration/toll_retail_map_")
    html = open(out).read()
    assert html.startswith("<!DOCTYPE html>") and "leaflet" in html.lower()
    custom = gen.create_html_map(str(tmp_path / "m.html"))
    assert custom == str(tmp_path / "m.html")


def test_load_data_without_inputs_leaves_everything_empty(gen, blocked, monkeypatch):
    gen.toll_plazas, gen.retail_outlets = [], []
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("x")))
    gen.load_data()
    assert gen.toll_plazas == [] and gen.retail_outlets == []


def test_load_data_all_sources(gen, monkeypatch, tmp_path):
    gen.toll_plazas, gen.retail_outlets = [], []
    ssri = tmp_path / "ssri.json"
    ssri.write_text(json.dumps([{"name": "S", "latitude": 1.0, "longitude": 2.0, "company": "IOCL", "has_cng": True},
                                {"name": "no", "latitude": None, "longitude": 2.0}]))
    real_open = open
    monkeypatch.setattr(tm, "open", lambda path, *a, **k: real_open(ssri, *a, **k), raising=False)
    frames = iter([pd.DataFrame({"name": ["A1"], "state": ["Goa"], "city": ["c"]}),
                   pd.DataFrame({"plaza_name": ["T1", "  ", None, "T2"], "state": ["Gujarat", "Gujarat", "Gujarat", "Atlantis"],
                                 "highway": ["NH8", "x", "x", "NH9"]})])
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: next(frames))
    gen.load_data()
    assert [o["name"] for o in gen.retail_outlets] == ["S", "A1"] and gen.retail_outlets[0]["has_cng"] is True
    assert gen.retail_outlets[1]["lat"] is None and gen.retail_outlets[1]["icon"] == "orange"
    t1, t2 = gen.toll_plazas
    assert abs(t1["lat"] - 22.5) <= 0.5 and abs(t1["lng"] - 72.5) <= 0.5               # state centroid +/- 0.5 deg jitter
    assert (t2["lat"], t2["lng"]) == (23.0, 79.0)                                        # unknown state -> fixed fallback
    assert t1["highway"] == "NH8"


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="load_data() still places toll plazas at a state centroid plus random jitter "
                          "(and (23, 79) for unknown states), which toll_coords.py documents as meaningless; "
                          "the distance script was changed to use only real coordinates")
def test_load_data_does_not_invent_toll_coordinates(gen, blocked, monkeypatch):
    gen.toll_plazas, gen.retail_outlets = [], []
    frames = iter([FileNotFoundError("x"), pd.DataFrame({"plaza_name": ["T1"], "state": ["Gujarat"], "highway": ["NH8"]})])

    def read_csv(*a, **k):
        f = next(frames)
        if isinstance(f, Exception):
            raise f
        return f
    monkeypatch.setattr(pd, "read_csv", read_csv)
    gen.load_data()
    assert gen.toll_plazas == []                                        # no coordinates in the file -> nothing to map


def test_map_run_and_main(blocked, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("x")))
    tm.main()
    assert list((tmp_path / "api-data-integration").glob("toll_retail_map_*.html"))
    assert "Map generation complete" in capsys.readouterr().out


# ------------------------------------------------------------------ create_toll_retail_distance_map
@pytest.fixture
def an():
    a = dm.TollRetailDistanceAnalyzer()
    a.toll_plazas = [{"id": 0, "name": "Near", "highway": "NH1", "state": "Goa", "lat": 15.0, "lng": 74.0, "type": "Toll Plaza"},
                     {"id": 1, "name": "Far", "highway": "NH2", "state": "Kerala", "lat": 10.0, "lng": 76.0, "type": "Toll Plaza"}]
    a.retail_outlets = [{"id": i, "name": f"O{i}", "company": "IOCL", "state": "Goa", "city": "x", "type": "Petrol Pump",
                         "lat": 15.0 + d * KM, "lng": 74.0, "has_cng": bool(i % 2), "petrol_price": None, "diesel_price": None}
                        for i, d in enumerate([0.5, 4.0, 9.0, 20.0, 40.0, 80.0])]
    a.calculate_distances()
    return a


def test_radius_stats_accumulate_across_plazas(an):
    s = an.stats
    assert (s["outlets_within_1km"], s["outlets_within_5km"], s["outlets_within_10km"]) == (1, 2, 3)
    assert (s["outlets_within_25km"], s["outlets_within_50km"]) == (4, 5)
    assert s["outlet_count"] == 6 and s["total_distances"] == 12
    near, far = an.distance_matrix
    assert near["min_distance"] == pytest.approx(0.5, abs=0.01) and far["outlets_10km"] == 0


def test_exact_radius_boundary_is_inclusive():
    a = dm.TollRetailDistanceAnalyzer()
    a.toll_plazas = [{"id": 0, "name": "T", "highway": "", "state": "", "lat": 0.0, "lng": 0.0}]
    a.retail_outlets = [{"id": 0, "name": "o", "company": "c", "city": "c", "has_cng": False, "lat": 0.0, "lng": 0.0}]
    a.calculate_distances()                                        # distance exactly 0 <= every radius
    assert a.stats["outlets_within_1km"] == a.stats["outlets_within_50km"] == 1


def test_haversine_wrapper(an):
    assert an.haversine_distance(0, 0, 0, 1) == pytest.approx(111.19, abs=0.05)
    assert an.haversine_distance(None, 0, 0, 1) == float("inf")


def test_summary_and_analysis_frames(an):
    s = an._summary_frame().set_index("Metric")["Value"]
    assert s["Toll Plazas"] == 0 and s["Retail Outlets"] == 6                    # stats['toll_count'] is only set by load_toll_plazas
    assert s["Total Distance Pairs"] == "12" and s["Outlets within 5km"] == "2"
    assert s["Avg outlets per toll (5km)"] == round(2 / max(0, 1), 2)
    an.stats["toll_count"] = 2
    assert an._summary_frame().set_index("Metric")["Value"]["Avg outlets per toll (5km)"] == 1.0
    f = an._distance_analysis_frame()
    assert list(f["Toll Plaza"]) == ["Near", "Far"] and f.loc[0, "Closest Outlet"] == "O0"
    assert f.loc[0, "Outlets 1km"] == 1 and f.loc[1, "Closest Outlet"] != "N/A"
    an.distance_matrix[1]["closest_outlets"] = []
    assert an._distance_analysis_frame().loc[1, "Closest Outlet"] == "N/A"
    u = an._underserved_frame()
    assert list(u["Toll Plaza"])[0] == "Near"                                    # sorted ascending by min distance (as the source keeps it)
    st = an._state_analysis_frame()
    assert set(st["State"]) == {"Goa", "Kerala"}


def test_export_distance_excel_and_html(an, blocked, tmp_path):
    an.stats["toll_count"] = 2
    path = an.export_distance_excel()
    assert path.startswith("./api-data-integration/TOLL_RETAIL_DISTANCE_ANALYSIS_")
    assert pd.ExcelFile(path).sheet_names == ["SUMMARY", "DISTANCE ANALYSIS", "UNDERSERVED PLAZAS", "STATE ANALYSIS"]
    out = an.create_html_map()
    assert out.startswith("./api-data-integration/") and open(out).read().startswith("<!DOCTYPE html>")
    assert an.create_html_map(str(tmp_path / "x.html")) == str(tmp_path / "x.html")


def test_load_ssri_data_prefers_107k_then_falls_back(monkeypatch, tmp_path):
    a = dm.TollRetailDistanceAnalyzer()
    big, small = tmp_path / "big.json", tmp_path / "small.json"
    big.write_text(json.dumps([{"id": 1, "name": "B", "latitude": "1.5", "longitude": 2.5, "company": "X"},
                               {"id": 2, "name": "no coords", "latitude": None, "longitude": 2.5}]))
    small.write_text(json.dumps([{"id": 9, "name": "S", "latitude": 3.5, "longitude": 4.5}]))
    import glob
    monkeypatch.setattr(glob, "glob", lambda pat: [str(big)] if "107k" in pat else [str(small)])
    assert a.load_ssri_data() is True
    assert [o["id"] for o in a.retail_outlets] == [1] and a.retail_outlets[0]["lat"] == 1.5
    b = dm.TollRetailDistanceAnalyzer()
    monkeypatch.setattr(glob, "glob", lambda pat: [] if "107k" in pat else [str(small)])
    assert b.load_ssri_data() is True and b.retail_outlets[0]["id"] == 9
    c = dm.TollRetailDistanceAnalyzer()
    monkeypatch.setattr(glob, "glob", lambda pat: [])
    assert c.load_ssri_data() is False
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    d = dm.TollRetailDistanceAnalyzer()
    monkeypatch.setattr(glob, "glob", lambda pat: [str(bad)])
    assert d.load_ssri_data() is False


def test_load_toll_plazas_failure_returns_false(monkeypatch):
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("x")))
    assert dm.TollRetailDistanceAnalyzer().load_toll_plazas() is False


def test_distance_run_stages(blocked, monkeypatch, tmp_path, capsys):
    a = dm.TollRetailDistanceAnalyzer()
    monkeypatch.setattr(a, "load_toll_plazas", lambda: False)
    a.run()
    assert "Failed to load toll plazas" in capsys.readouterr().out
    monkeypatch.setattr(a, "load_toll_plazas", lambda: True)
    monkeypatch.setattr(a, "load_ssri_data", lambda: False)
    a.run()
    assert "Failed to load SSRI data" in capsys.readouterr().out
    a.toll_plazas = [{"id": 0, "name": "T", "highway": "NH", "state": "Goa", "lat": 15.0, "lng": 74.0}]
    a.retail_outlets = [{"id": 0, "name": "o", "company": "c", "city": "c", "state": "Goa", "type": "Petrol Pump",
                         "has_cng": False, "lat": 15.01, "lng": 74.0, "petrol_price": None, "diesel_price": None}]
    monkeypatch.setattr(a, "load_ssri_data", lambda: True)
    a.run()
    assert "Analysis Complete" in capsys.readouterr().out
    assert list((tmp_path / "api-data-integration").glob("TOLL_RETAIL_DISTANCE_ANALYSIS_*.xlsx"))


def test_distance_main(monkeypatch):
    seen = {}
    monkeypatch.setattr(dm.TollRetailDistanceAnalyzer, "run", lambda self: seen.setdefault("ran", True))
    dm.main()
    assert seen == {"ran": True}
