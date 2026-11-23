"""validate_outlets_against_ssri (fuzzy matching against an SSRI baseline) and hybrid_aggregator
(OSM/PPAC dedup + exports). Offline: files live under tmp_path, the OSM POST is faked."""
import json
import math

import pandas as pd
import pytest

import hybrid_aggregator as ha
import validate_outlets_against_ssri as v


# ------------------------------------------------------------------ validator helpers
@pytest.fixture
def val(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    return v.SSRIOutletValidator()


def test_normalize_name():
    n = v.SSRIOutletValidator.normalize_name
    assert n("  Shri  Ram, Filling-Station!! ") == "shri ram fillingstation"
    assert n("") == "" and n(None) == ""
    assert n("A\tB\nC") == "a b c"


def test_similarity_identical_empty_and_partial(val):
    assert val.calculate_similarity("Ram Fuels", "ram fuels!") == 1.0
    assert val.calculate_similarity("", "x") == 0 and val.calculate_similarity("x", None) == 0
    assert 0 < val.calculate_similarity("ram fuels", "ram filling") < 1


def test_haversine_known_distance_and_zero_guard():
    h = v.SSRIOutletValidator.haversine_distance
    assert h(0.0001, 0.0001, 0.0001, 1.0001) == pytest.approx(111.19, abs=0.1)     # 1 degree of longitude at the equator
    assert h(28.6, 77.2, 28.6, 77.2) == pytest.approx(0, abs=1e-9)
    assert h(0, 77, 28, 77) == float("inf") and h(28, 77, 28, None) == float("inf")


def write_ssri(tmp_path, rows, sub="outlet_data_ssri_107k", name="ssri_complete_pumps_1.csv"):
    d = tmp_path / sub
    d.mkdir()
    pd.DataFrame(rows).to_csv(d / name, index=False)


def test_load_ssri_database_filters_and_pattern_priority(val, tmp_path):
    assert val.load_ssri_database() is False                         # no files at all
    write_ssri(tmp_path, [
        {"name": " A ", "state": "Kerala", "latitude": 10.0, "longitude": 76.0, "company": "IOCL"},
        {"name": "B", "state": "Kerala", "latitude": None, "longitude": 76.0, "company": "x"},    # NaN lat -> dropped
        {"name": "C", "state": "Kerala", "latitude": 0, "longitude": 0, "company": "x"},          # zero coords -> dropped
        {"name": "D", "state": "Goa", "latitude": "bad", "longitude": 1, "company": "x"},        # unparsable -> dropped
    ])
    assert val.load_ssri_database() is True
    assert val.ssri_outlets == [{"name": "A", "state": "Kerala", "latitude": 10.0, "longitude": 76.0, "company": "IOCL"}]


def test_load_ssri_database_falls_back_to_second_pattern_and_survives_bad_file(val, tmp_path):
    write_ssri(tmp_path, [{"name": "Z", "state": "S", "latitude": 1.0, "longitude": 2.0, "company": "c"}],
               sub="outlet_data_ssri", name="ssri_petrol_pumps_9.csv")
    assert val.load_ssri_database() is True and val.ssri_outlets[0]["name"] == "Z"
    (tmp_path / "outlet_data_ssri_107k").mkdir()
    (tmp_path / "outlet_data_ssri_107k" / "ssri_complete_pumps_1.csv").write_bytes(b"")
    assert val.load_ssri_database() is False                          # first pattern wins and is unreadable


def write_extracted(tmp_path, rows):
    d = tmp_path / "outlet_data_cashatpos"
    d.mkdir()
    pd.DataFrame(rows).to_csv(d / "cashatpos_fuel_stations_1.csv", index=False)


def test_load_extracted_outlets(val, tmp_path):
    assert val.load_extracted_outlets() is False
    write_extracted(tmp_path, [
        {"name": "A", "state": "Kerala", "latitude": 10.0, "longitude": 76.0},
        {"name": "B", "state": "Kerala", "latitude": None, "longitude": None},
        {"name": "E", "state": "Goa", "latitude": 0.0, "longitude": 5.0},           # zero lat -> no coords
    ])
    assert val.load_extracted_outlets() is True
    assert [(o["name"], o["has_coords"]) for o in val.extracted_outlets] == [("A", True), ("B", False), ("E", False)]


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="blank name/state cells read from CSV are NaN and str(NaN) == 'nan', which is truthy, "
                          "so the `if not (name and state)` guard in load_extracted_outlets never skips them")
def test_load_extracted_outlets_skips_rows_without_name_or_state(val, tmp_path):
    write_extracted(tmp_path, [{"name": "", "state": "Kerala", "latitude": 1.0, "longitude": 2.0},
                               {"name": "D", "state": "", "latitude": 1.0, "longitude": 2.0},
                               {"name": "ok", "state": "Goa", "latitude": 1.0, "longitude": 2.0}])
    assert val.load_extracted_outlets() is True
    assert [o["name"] for o in val.extracted_outlets] == ["ok"]


def test_load_extracted_outlets_without_coordinate_columns(val, tmp_path):
    write_extracted(tmp_path, [{"name": "A", "state": "Kerala"}])
    assert val.load_extracted_outlets() is True
    assert val.extracted_outlets[0]["has_coords"] is False


def ex(name, state="Kerala", lat=0, lon=0, coords=False):
    return {"name": name, "state": state, "latitude": lat, "longitude": lon, "has_coords": coords}


def ss(name, state="Kerala", lat=10.0, lon=76.0, company="IOCL"):
    return {"name": name, "state": state, "latitude": lat, "longitude": lon, "company": company}


def test_validate_returns_none_pair_when_either_side_empty(val):
    assert val.validate_against_ssri() == (None, None)
    val.ssri_outlets = [ss("a")]
    assert val.validate_against_ssri() == (None, None)


def test_validate_name_only_threshold_and_state_gate(val):
    val.ssri_outlets = [ss("Ram Fuels Kochi"), ss("Ram Fuels Kochi", state="Goa")]
    val.extracted_outlets = [ex("Ram Fuels Kochi"), ex("Totally Different"), ex("Ram Fuels Kochi", state="Assam")]
    matched, new = val.validate_against_ssri()
    assert [m[0]["name"] for m in matched] == ["Ram Fuels Kochi"] and matched[0][1]["state"] == "Kerala"
    assert matched[0][2] == 1.0
    assert [o["state"] for o in new] == ["Kerala", "Assam"]            # no SSRI row in Assam; dissimilar name


def test_validate_threshold_depends_on_coordinates(val):
    # name similarity 0.60: passes the name-only threshold (0.55) ...
    val.ssri_outlets = [ss("abcdefghij", lat=10.0, lon=76.0)]
    sim = val.calculate_similarity("abcdefxxxx", "abcdefghij")
    assert 0.55 < sim < 0.65
    val.extracted_outlets = [ex("abcdefxxxx")]
    assert len(val.validate_against_ssri()[0]) == 1
    # ... but with coordinates 100 km away the score is 0.7*sim + 0 < 0.65 -> new outlet
    val.extracted_outlets = [ex("abcdefxxxx", lat=11.0, lon=77.0, coords=True)]
    matched, new = val.validate_against_ssri()
    assert matched == [] and len(new) == 1


def test_validate_proximity_boosts_score(val):
    val.ssri_outlets = [ss("Shell Point", lat=10.0, lon=76.0)]
    val.extracted_outlets = [ex("Shell Point", lat=10.0, lon=76.0, coords=True)]
    m, _ = val.validate_against_ssri()
    assert m[0][2] == pytest.approx(1.0)                              # 0.7*1 + 0.3*1
    val.extracted_outlets = [ex("Shell Point", lat=10.0, lon=76.0 + 2.5 / 111.0 / math.cos(math.radians(10)), coords=True)]
    m, _ = val.validate_against_ssri()
    assert m[0][2] == pytest.approx(0.7 + 0.3 * 0.5, abs=0.01)         # 2.5 km of 5 km -> half proximity


def test_validate_picks_best_of_several_candidates(val):
    val.ssri_outlets = [ss("Ram Fuel"), ss("Ram Fuels Kochi"), ss("Other")]
    val.extracted_outlets = [ex("Ram Fuels Kochi")]
    m, _ = val.validate_against_ssri()
    assert m[0][1]["name"] == "Ram Fuels Kochi"


def test_validate_tie_keeps_the_first_candidate(val):
    val.ssri_outlets = [ss("Shell Point", company="FIRST"), ss("Shell Point", company="SECOND")]
    val.extracted_outlets = [ex("Shell Point")]
    m, _ = val.validate_against_ssri()
    assert m[0][1]["company"] == "FIRST"                              # strict '>' : an equal score never replaces the best


def test_validate_prints_progress_every_100(val, capsys):
    val.ssri_outlets = [ss("a")]
    val.extracted_outlets = [ex("zzzz")] * 100
    val.validate_against_ssri()
    assert "100" in capsys.readouterr().out


def test_export_report_sheets_and_quality_labels(val, tmp_path):
    val.ssri_outlets = [ss("a"), ss("b")]
    val.extracted_outlets = [ex("a1", coords=True, lat=1.5, lon=2.5), ex("a2"), ex("a3"), ex("n1", state="Goa")]
    matched = [(val.extracted_outlets[0], ss("a1"), 0.95), (val.extracted_outlets[1], ss("a2"), 0.8),
               (val.extracted_outlets[2], ss("a3"), 0.7)]
    new = [val.extracted_outlets[3]]
    path = val.export_comprehensive_report(matched, new)
    xl = pd.ExcelFile(path)
    sh = lambda n: pd.read_excel(path, sheet_name=n, keep_default_na=False)   # noqa: E731
    assert xl.sheet_names == ["SUMMARY", "MATCHES", "NEW OUTLETS", "STATE ANALYSIS"]
    summ = dict(zip(*[sh("SUMMARY")[c] for c in ("Metric", "Value")]))
    assert str(summ["Coverage %"]) == "75.0%"
    assert [int(summ[k]) for k in ("High Confidence (>90%)", "Medium Confidence (75-90%)", "Low Confidence (65-75%)")] == [1, 1, 1]
    assert list(sh("MATCHES")["Quality"]) == ["High", "Medium", "Low"]
    assert sh("NEW OUTLETS")["Latitude"].iloc[0] == "N/A"
    st = sh("STATE ANALYSIS").set_index("State")
    assert st.loc["Kerala", "Total"] == 3 and st.loc["Kerala", "In SSRI"] == 3 and st.loc["Goa", "New"] == 1
    assert st.loc["Goa", "Coverage"] == "0.0%"


def test_export_report_formats_coordinates_for_new_outlets_with_coords(val):
    val.extracted_outlets = [ex("n", coords=True, lat=1.5, lon=2.5)]
    path = val.export_comprehensive_report([], val.extracted_outlets)
    xl = pd.ExcelFile(path)
    assert "MATCHES" not in xl.sheet_names
    lat = pd.read_excel(path, sheet_name="NEW OUTLETS")["Latitude"].iloc[0]
    assert float(lat) == 1.5


def test_print_summary_and_run(val, tmp_path, capsys):
    val.print_validation_summary([(ex("a"), ss("a"), 0.9)], [ex("b", state="Goa")])
    assert capsys.readouterr().out
    val.run()                                                          # no inputs -> returns quietly
    write_ssri(tmp_path, [{"name": "Ram Fuels", "state": "Kerala", "latitude": 10.0, "longitude": 76.0, "company": "IOCL"}])
    write_extracted(tmp_path, [{"name": "Ram Fuels", "state": "Kerala"}])
    val.run()
    assert list(tmp_path.glob("SSRI_VALIDATION_REPORT_*.xlsx"))


def test_run_returns_when_validation_yields_nothing(val, tmp_path, monkeypatch):
    monkeypatch.setattr(val, "load_ssri_database", lambda: True)
    monkeypatch.setattr(val, "load_extracted_outlets", lambda: True)
    val.run()
    assert not list(tmp_path.glob("SSRI_VALIDATION_REPORT_*.xlsx"))


# ------------------------------------------------------------------ hybrid_aggregator
OSM = """<osm>
 <node lat="10.5" lon="76.5"><tag k="amenity" v="fuel"/><tag k="name" v="Named Pump"/></node>
 <node lat="11.0" lon="77.0"/>
 <node lat="" lon="77.0"/>
</osm>"""


@pytest.fixture
def agg():
    return ha.HybridOutletAggregator()


def test_parse_osm_response(agg):
    out = agg._parse_osm_response(OSM)
    assert [o["name"] for o in out] == ["Named Pump", "OSM Fuel Station"]      # blank-lat node dropped, default name used
    assert out[0] == {"name": "Named Pump", "latitude": 10.5, "longitude": 76.5, "source": "OpenStreetMap",
                      "company": "Unknown", "city": None, "state": None}
    assert agg._parse_osm_response("<not xml") == []


def test_calculate_distance(agg):
    assert agg.calculate_distance(0, 0, 0, 1) == pytest.approx(111.19, abs=0.05)
    assert agg.calculate_distance(10, 20, 10, 20) == 0
    assert agg.calculate_distance(0, 0, 0, 180) == pytest.approx(math.pi * 6371, rel=1e-9)


def test_dedup_radius_priority_and_missing_coordinates(agg):
    o = lambda src, lat, lon, name="x": {"name": name, "source": src, "latitude": lat, "longitude": lon}   # noqa: E731
    near = 0.4 / 111.19                                                     # ~0.4 km north
    far = 0.6 / 111.19
    out = agg.deduplicate_outlets([
        o("OpenStreetMap", 10 + near, 20, "osm-near"), o("PPAC", 10, 20, "ppac"),
        o("OpenStreetMap", 10 + far, 20, "osm-far"), o("Google", 30, 30, "g"),
        o("OpenStreetMap", None, None, "no-coords-1"), o("OpenStreetMap", None, None, "no-coords-2"),
    ])
    names = [x["name"] for x in out]
    assert "ppac" in names and "osm-near" not in names                       # PPAC outranks OSM, 0.4 km < 0.5 km radius
    assert "osm-far" in names                                                # 0.6 km survives
    assert "no-coords-1" in names and "no-coords-2" in names                 # coordinate-less rows are never merged
    assert agg.stats["duplicates_removed"] == 1 and agg.stats["final_unique"] == len(out) == 5
    assert agg.deduplicate_outlets([]) == []


def test_dedup_radius_boundary(agg):
    km_per_deg = 6371 * math.pi / 180
    mk = lambda d: [{"source": "PPAC", "latitude": 10.0, "longitude": 20.0},      # noqa: E731
                    {"source": "PPAC", "latitude": 10.0 + d / km_per_deg, "longitude": 20.0}]
    assert len(agg.deduplicate_outlets(mk(0.4999))) == 1                         # just inside 0.5 km: merged
    assert len(agg.deduplicate_outlets(mk(0.5001))) == 2                         # just outside: both kept
    agg.dedup_distance_km = 0
    assert len(agg.deduplicate_outlets(mk(0.0))) == 2                            # strict '<': zero radius merges nothing
    equator = [{"source": "PPAC", "latitude": 0.0, "longitude": 5.0}] * 2
    agg.dedup_distance_km = 0.5
    assert len(agg.deduplicate_outlets(equator)) == 2                            # latitude 0.0 is falsy: treated as 'no coordinates'


def test_dedup_unknown_source_sorts_last(agg):
    out = agg.deduplicate_outlets([
        {"source": "Mystery", "name": "m", "latitude": 5.0, "longitude": 5.0},
        {"source": "OpenStreetMap", "name": "o", "latitude": 5.0, "longitude": 5.0},
    ])
    assert [x["name"] for x in out] == ["o"]


def test_load_ppac_data(agg, tmp_path):
    assert agg.load_ppac_data() == [] and agg.load_ppac_data("") == []
    assert agg.load_ppac_data(str(tmp_path / "missing.csv")) == []
    p = tmp_path / "p.csv"
    pd.DataFrame({"outlet_name": ["A", "B", "C"], "lat": [1.0, None, 3.0], "lng": [2.0, 2.0, 0.0],
                  "operator": ["IOCL", "BPCL", "HPCL"], "location": ["x", "y", "z"], "state": ["s", "s", "s"]}).to_csv(p, index=False)
    out = agg.load_ppac_data(str(p))
    assert [o["name"] for o in out] == ["A"]                                 # missing lat and zero lng rows dropped
    assert out[0]["company"] == "IOCL" and out[0]["city"] == "x" and out[0]["source"] == "PPAC"
    assert agg.stats["ppac"] == 1
    bad = tmp_path / "bad.csv"
    bad.write_bytes(b"")
    assert agg.load_ppac_data(str(bad)) == []


def test_google_requires_key(agg):
    assert agg.fetch_google_maps_data() == [] and agg.fetch_google_maps_data("k") == []


class R:
    def __init__(self, code, text=""):
        self.status_code, self.text = code, text


def test_fetch_osm_data_retries_and_regions(agg, monkeypatch):
    calls, sleeps = [], []
    seq = iter([R(500), R(200, OSM), R(200, OSM), R(200, OSM)])

    def post(url, data=None, timeout=None):
        calls.append((url, timeout, data))
        return next(seq)

    monkeypatch.setattr(ha.requests, "post", post)
    monkeypatch.setattr(ha.time, "sleep", lambda s: sleeps.append(s))
    out = agg.fetch_osm_data()
    assert len(out) == 6 and agg.stats["osm"] == 6                          # 3 regions x 2 valid nodes
    assert len(calls) == 4 and sleeps == [3]                                # first region retried once after a 500
    assert calls[0][0] == "https://overpass-api.de/api/interpreter" and calls[0][1] == 60
    assert "[bbox:23,68,35,97]" in calls[0][2]


def test_fetch_osm_data_error_handling(agg, monkeypatch):
    sleeps = []
    monkeypatch.setattr(ha.time, "sleep", lambda s: sleeps.append(s))

    def timeout(*a, **k):
        raise ha.requests.exceptions.Timeout()
    monkeypatch.setattr(ha.requests, "post", timeout)
    assert agg.fetch_osm_data(retries=2) == []
    assert sleeps == [5] * 6                                                # 3 regions x 2 attempts, timeout backoff = 5 s
    sleeps.clear()

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(ha.requests, "post", boom)
    assert agg.fetch_osm_data(retries=1) == [] and sleeps == [2, 2, 2]


def test_aggregate_combines_sources(agg, monkeypatch, tmp_path):
    p = tmp_path / "p.csv"
    pd.DataFrame({"name": ["A"], "latitude": [10.5], "longitude": [76.5]}).to_csv(p, index=False)
    monkeypatch.setattr(agg, "fetch_osm_data", lambda: agg._parse_osm_response(OSM))
    out = agg.aggregate(ppac_csv=str(p), google_api_key="k")
    assert sorted(o["name"] for o in out) == ["A", "OSM Fuel Station"]       # OSM 'Named Pump' (same spot as PPAC) deduplicated


def test_export_all_formats(agg, tmp_path):
    assert agg.export_all_formats(str(tmp_path / "none")) is None
    agg.deduped_outlets = [
        {"name": "A", "latitude": 10.0, "longitude": 76.0, "source": "PPAC", "company": "c", "city": "x", "state": "s"},
        {"name": "B", "latitude": None, "longitude": None, "source": "OpenStreetMap", "company": "Unknown", "city": None, "state": None},
    ]
    agg.stats.update(ppac=1, osm=1, duplicates_removed=3)
    out = tmp_path / "o"
    assert agg.export_all_formats(str(out)) == str(out)
    gj = json.loads(next(out.glob("*.geojson")).read_text())
    assert len(gj["features"]) == 1 and gj["features"][0]["geometry"]["coordinates"] == [76.0, 10.0]
    stats = json.loads(next(out.glob("*stats*.json")).read_text())
    assert stats["total_outlets"] == 2 and stats["with_coordinates"] == 1
    assert stats["sources"] == {"ppac": 1, "osm": 1, "google": 0, "duplicates_removed": 3}
    js = next(out.glob("*.js")).read_text()
    assert "duplicates_removed: 3" in js and "total: 2," in js
    assert len(json.loads(next(p for p in out.glob("hybrid_outlets_*.json") if "stats" not in p.name).read_text())) == 2


def test_export_swallows_exceptions_and_summary_main(agg, tmp_path, monkeypatch, capsys):
    agg.deduped_outlets = [{"name": "A"}]                                    # no latitude column -> KeyError inside writers
    assert agg.export_all_formats(str(tmp_path / "bad")) is None
    agg.print_summary()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ha.HybridOutletAggregator, "fetch_osm_data", lambda self: [])
    ha.main()                                                                # no outlets path
    monkeypatch.setattr(ha.HybridOutletAggregator, "fetch_osm_data",
                        lambda self: [{"name": "x", "latitude": 1.0, "longitude": 2.0, "source": "OpenStreetMap",
                                       "company": "Unknown", "city": None, "state": None}])
    ha.main()
    assert any((tmp_path / "outlet_data_hybrid").glob("hybrid_outlets_*.csv"))
