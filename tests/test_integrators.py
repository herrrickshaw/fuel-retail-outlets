"""integrate_toll_retail_database (toll plaza <-> outlet service zones) and the I/O half of
integrate_multi_source_database (loaders, exports, pipeline). All paths are tmp_path."""
import json

import pandas as pd
import pytest

import integrate_multi_source_database as ims
import integrate_toll_retail_database as itr

KM = 1 / 111.195


# ------------------------------------------------------------------ TollRetailIntegrator
@pytest.fixture
def tri(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    return itr.TollRetailIntegrator()


def outlet(lat, lon, typ="Petrol Pump", state="Gujarat"):
    return {"name": "o", "type": typ, "state": state, "city": "c", "latitude": lat, "longitude": lon}


def test_load_toll_plazas_filters_blank_and_header_rows(tri, tmp_path):
    p = tmp_path / "t.csv"
    pd.DataFrame({"plaza_name": [" A ", "", None, "PLAZA_NAME", "  ", "B"], "highway": ["NH1", "x", "x", "x", "x", None],
                  "state": ["Gujarat", "g", "g", "g", "g", "Goa"]}).to_csv(p, index=False)
    assert tri.load_toll_plazas(str(p)) is True
    assert [t["name"] for t in tri.toll_plazas] == ["A", "B"]
    assert tri.toll_plazas[0]["highway"] == "NH1" and tri.toll_plazas[0]["latitude"] is None
    assert tri.stats["toll_plazas_loaded"] == 2


def test_load_toll_plazas_missing_file(tri, tmp_path):
    assert tri.load_toll_plazas(str(tmp_path / "nope.csv")) is False


def test_find_nearby_radius_boundary_and_sorting_inputs(tri):
    tri.retail_outlets = [outlet(10 + 4.9 * KM, 20), outlet(10 + 5.1 * KM, 20), outlet(None, 20), outlet(10, 0)]
    plaza = {"latitude": 10.0, "longitude": 20.0}
    near5 = tri.find_nearby_outlets(plaza, 5.0)
    assert len(near5) == 1 and near5[0]["distance_km"] == pytest.approx(4.9, abs=0.01)
    assert len(tri.find_nearby_outlets(plaza, 25.0)) == 2                      # outlet at longitude 0 is falsy -> skipped
    assert tri.find_nearby_outlets(plaza) == tri.find_nearby_outlets(plaza, 25.0)   # default radius is 25 km
    assert tri.find_nearby_outlets({"latitude": None, "longitude": 20.0}) == []
    assert tri.find_nearby_outlets({"latitude": 10.0, "longitude": 0}) == []


def test_haversine_wrapper(tri):
    assert tri.haversine_distance(0.001, 0.001, 0.001, 1.001) == pytest.approx(111.195, abs=0.01)
    assert tri.haversine_distance(None, 1, 2, 3) == float("inf")


def test_geocode_known_state_stays_within_jitter_and_unknown_falls_back(tri, monkeypatch):
    seq = iter([0.5, -0.25, 3.0, -2.0])
    monkeypatch.setattr(itr.np.random, "uniform", lambda a, b: next(seq))
    tri.toll_plazas = [{"state": "Gujarat"}, {"state": "Atlantis"}]
    tri.geocode_toll_plazas()
    assert (tri.toll_plazas[0]["latitude"], tri.toll_plazas[0]["longitude"]) == (22.5 + 0.5, 72.5 - 0.25)
    assert (tri.toll_plazas[1]["latitude"], tri.toll_plazas[1]["longitude"]) == (23.0 + 3.0, 79.0 - 2.0)


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="geocode_toll_plazas() still invents coordinates (state centroid + random jitter, "
                          "(23, 79) for unknown states). toll_coords.py documents that such points make every "
                          "distance meaningless and the sibling scripts were changed to skip plazas without "
                          "real coordinates")
def test_geocode_does_not_invent_coordinates(tri):
    tri.toll_plazas = [{"state": "Gujarat", "latitude": None, "longitude": None}]
    tri.geocode_toll_plazas()
    assert tri.toll_plazas[0]["latitude"] is None


def test_integrate_counts_by_ring_and_type(tri):
    tri.toll_plazas = [{"name": "P", "highway": "NH", "state": "Gujarat", "latitude": 10.0, "longitude": 20.0},
                       {"name": "NoCoord", "highway": "NH", "state": "Goa", "latitude": None, "longitude": None}]
    tri.retail_outlets = [outlet(10 + 1 * KM, 20), outlet(10 + 2 * KM, 20, typ="Cash@PoS ATM Station"),
                          outlet(10 + 8 * KM, 20), outlet(10 + 20 * KM, 20), outlet(10 + 40 * KM, 20)]
    tri.integrate_toll_and_outlets()
    p, n = tri.integrated_data
    assert (p["petrol_pumps_5km"], p["atm_stations_5km"], p["total_outlets_5km"],
            p["total_outlets_10km"], p["total_outlets_25km"]) == (1, 1, 2, 3, 4)
    assert n["total_outlets_25km"] == 0
    assert tri.stats["outlets_within_5km"] == 2 and tri.stats["outlets_within_10km"] == 3
    assert tri.stats["outlets_within_25km"] == 4 and tri.stats["integrations_created"] == 2


def test_load_retail_outlets_without_sources_is_still_true(tri, monkeypatch):
    real_open = open
    monkeypatch.setattr(itr, "open", lambda path, *a, **k: (_ for _ in ()).throw(FileNotFoundError(path))
                        if str(path).startswith("/Users/") else real_open(path, *a, **k), raising=False)
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("x")))
    assert tri.load_retail_outlets() is True
    assert tri.retail_outlets == [] and tri.stats["retail_outlets_loaded"] == 0


def test_load_retail_outlets_all_three_sources(tri, monkeypatch, tmp_path):
    ssri = tmp_path / "ssri.json"
    ssri.write_text(json.dumps([{"name": "S", "latitude": 1.0, "longitude": 2.0, "company": "IOCL", "state": "Goa"},
                                {"name": "NoCoord", "latitude": None, "longitude": 2.0}]))
    real_open = open
    monkeypatch.setattr(itr, "open", lambda path, *a, **k: real_open(ssri, *a, **k), raising=False)
    frames = iter([pd.DataFrame({"name": ["B1", "B2"], "state": ["Goa", "Goa"], "city": ["c", "c"],
                                 "latitude": [3.0, 0.0], "longitude": [4.0, 4.0]}),
                   pd.DataFrame({"name": ["A1"], "state": ["Goa"], "city": ["c"]})])
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: next(frames))
    assert tri.load_retail_outlets() is True
    assert [(o["type"], o["name"]) for o in tri.retail_outlets] == [
        ("Petrol Pump", "S"), ("BPCL Dealer", "B1"), ("Cash@PoS ATM Station", "A1")]
    assert tri.retail_outlets[2]["latitude"] is None                          # ATM rows carry no coordinates
    assert tri.stats["retail_outlets_loaded"] == 3


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="a BPCL row with a blank latitude is NaN, and NaN is truthy, so "
                          "`if outlet['latitude'] and outlet['longitude']` keeps it as an outlet 'with coordinates'")
def test_load_retail_outlets_skips_bpcl_rows_with_blank_coordinates(tri, monkeypatch):
    real_open = open
    monkeypatch.setattr(itr, "open", lambda path, *a, **k: (_ for _ in ()).throw(FileNotFoundError(path))
                        if str(path).startswith("/Users/") else real_open(path, *a, **k), raising=False)
    frames = iter([pd.DataFrame({"name": ["B2"], "state": ["Goa"], "city": ["c"], "latitude": [float("nan")], "longitude": [4.0]}),
                   pd.DataFrame({"name": ["A"], "state": ["Goa"], "city": ["c"]})])
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: next(frames))
    tri.load_retail_outlets()
    assert [o["name"] for o in tri.retail_outlets if o["type"] == "BPCL Dealer"] == []


@pytest.mark.xfail(strict=True, raises=KeyError,
                   reason="export_to_excel() sorts the TOLL PLAZAS frame by 'Total Outlets (5km)' even when no "
                          "plaza was integrated, so an empty run raises KeyError instead of writing the SUMMARY sheet")
def test_export_with_no_integrated_plazas_still_writes_summary(tri, tmp_path):
    tri.export_to_excel(str(tmp_path / "e.xlsx"))


def test_export_to_excel_sheets_and_averages(tri, tmp_path):
    tri.toll_plazas = [{"name": "P", "highway": "NH", "state": "Gujarat"}, {"name": "Q", "highway": "NH", "state": "Goa"}]
    tri.retail_outlets = [outlet(10, 20), outlet(None, None, typ="BPCL Dealer", state="Goa"),
                          outlet(None, None, typ="Cash@PoS ATM Station", state="Goa")]
    tri.stats.update(toll_plazas_loaded=2, retail_outlets_loaded=3, integrations_created=2,
                     outlets_within_5km=3, outlets_within_10km=4, outlets_within_25km=5)
    tri.integrated_data = [
        {"toll_plaza_name": "P", "highway": "NH", "state": "Gujarat", "latitude": 10.1234567, "longitude": 20.0,
         "petrol_pumps_5km": 2, "atm_stations_5km": 1, "total_outlets_5km": 3, "total_outlets_10km": 4, "total_outlets_25km": 5},
        {"toll_plaza_name": "Q", "highway": "NH", "state": "Goa", "latitude": None, "longitude": None,
         "petrol_pumps_5km": 0, "atm_stations_5km": 0, "total_outlets_5km": 0, "total_outlets_10km": 0, "total_outlets_25km": 0},
    ]
    path = tmp_path / "x.xlsx"
    assert tri.export_to_excel(str(path)) == str(path)
    sh = lambda n: pd.read_excel(path, sheet_name=n)   # noqa: E731
    assert pd.ExcelFile(path).sheet_names == ["SUMMARY", "TOLL PLAZAS", "STATE ANALYSIS", "OUTLET TYPES"]
    summ = dict(zip(sh("SUMMARY")["Metric"], sh("SUMMARY")["Value"]))
    assert summ["Petrol Pumps (SSRI)"] == 1 and summ["BPCL Dealers"] == 1 and summ["Cash@PoS ATM Stations"] == 1
    assert summ["Avg Outlets per Toll (5km)"] == 1.5 and summ["Avg Outlets per Toll (25km)"] == 2.5
    tolls = sh("TOLL PLAZAS")
    assert list(tolls["Plaza Name"]) == ["P", "Q"] and tolls.loc[0, "Latitude"] == 10.123457
    assert pd.isna(tolls.loc[1, "Latitude"])
    st = sh("STATE ANALYSIS").set_index("State")
    assert st.loc["Goa", "BPCL Dealers"] == 1 and st.loc["Gujarat", "Avg Outlets per Toll (5km)"] == 3.0
    types = sh("OUTLET TYPES").set_index("Type")
    assert types.loc["Petrol Pump", "With Coordinates"] == 1 and types.loc["BPCL Dealer", "With Coordinates"] == 0


def test_export_default_name_and_summary_and_run(tri, tmp_path, monkeypatch, capsys):
    tri.print_summary()                                                     # nothing integrated yet
    tri.stats["integrations_created"] = 1
    tri.print_summary()
    tri.integrated_data = [{"toll_plaza_name": "P", "highway": "NH", "state": "Goa", "latitude": 1.0, "longitude": 2.0,
                            "petrol_pumps_5km": 0, "atm_stations_5km": 0, "total_outlets_5km": 0,
                            "total_outlets_10km": 0, "total_outlets_25km": 0}]
    tri.toll_plazas = [{"state": "Goa"}]
    assert tri.export_to_excel().startswith("./TOLL_RETAIL_INTEGRATION_")
    assert list(tmp_path.glob("TOLL_RETAIL_INTEGRATION_*.xlsx"))
    tri.toll_plazas, tri.integrated_data = [], []
    assert tri.run() is None                                                # /Users/... toll csv does not exist
    monkeypatch.setattr(tri, "load_toll_plazas", lambda p: True)
    monkeypatch.setattr(tri, "load_retail_outlets", lambda: False)
    tri.toll_plazas = [{"name": "P", "highway": "NH", "state": "Gujarat"}]
    (tmp_path / "api-data-integration").mkdir()
    out = tri.run()
    assert out.startswith("./api-data-integration/TOLL_RETAIL_INTEGRATION_")


def test_itr_main(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    called = {}
    monkeypatch.setattr(itr.TollRetailIntegrator, "run", lambda self: called.setdefault("ran", True))
    itr.main()
    assert called == {"ran": True}


# ------------------------------------------------------------------ MultiSourceDatabaseIntegrator I/O
@pytest.fixture
def msi():
    return ims.MultiSourceDatabaseIntegrator()


def test_loaders_success_and_failure(msi, tmp_path):
    j = tmp_path / "s.json"
    j.write_text(json.dumps([{"name": "a"}]))
    assert msi.load_ssri_data(str(j)) is True and msi.ssri_data == [{"name": "a"}]
    assert msi.load_ssri_data(str(tmp_path / "nope.json")) is False
    c = tmp_path / "b.csv"
    pd.DataFrame({"name": ["b"], "latitude": [1.0]}).to_csv(c, index=False)
    assert msi.load_bpcl_data(str(c)) is True and msi.bpcl_data == [{"name": "b", "latitude": 1.0}]
    assert msi.load_bpcl_data(str(tmp_path / "nope.csv")) is False
    x = tmp_path / "p.xlsx"
    pd.DataFrame([["m"] * 2] * 7 + [["State", "Count"], ["Goa", 5], [None, None]]).to_excel(x, header=False, index=False)
    assert msi.load_ppac_data(str(x)) is True
    assert list(msi.ppac_data.columns) == ["State", "Count"] and len(msi.ppac_data) == 1
    assert msi.load_ppac_data(str(tmp_path / "nope.xlsx")) is False


def test_find_nearby_defaults_and_inputs(msi):
    msi.unified_database = [{"company": "bpcl ", "latitude": 20.0, "longitude": 80.0}, {"company": "BPCL"}]
    assert msi.find_nearby_pumps({"company": "BPCL", "latitude": 20.0 + 0.4 * KM, "longitude": 80.0}) == [0]
    assert msi.find_nearby_pumps({"company": "BPCL", "latitude": 20.0 + 0.6 * KM, "longitude": 80.0}) == []
    assert msi.find_nearby_pumps({"company": "IOCL", "latitude": 20.0, "longitude": 80.0}) == []        # brand gate
    assert msi.find_nearby_pumps({"company": "IOCL", "latitude": 20.0, "longitude": 80.0}, same_company=False) == [0]
    assert msi.find_nearby_pumps({"company": "BPCL", "latitude": 0, "longitude": 80.0}) == []
    assert msi.find_nearby_pumps({"company": "BPCL", "latitude": 20.0, "longitude": 80.0}, search_radius_km=0.0) == [0]


def test_enrichment_only_fills_blank_fields(msi):
    msi.ssri_data = [{"name": "a", "company": "BPCL", "latitude": 20.0, "longitude": 80.0}]
    msi.bpcl_data = [{"company": "BPCL", "latitude": 20.0, "longitude": 80.0, "customer_code": "C1", "postal_code": "P1"},
                     {"company": "BPCL", "latitude": 20.0, "longitude": 80.0, "customer_code": "C2", "postal_code": "P2"}]
    msi.integrate_databases()
    rec = msi.unified_database[0]
    assert (rec["customer_code"], rec["postal_code"]) == ("C1", "P1")        # second duplicate must not overwrite
    assert msi.dedup_stats == {"total_records": 1, "duplicates_found": 2, "unique_records": 1,
                               "ssri_records": 1, "bpcl_records": 0, "ppac_records": 0}


def test_export_unified_database(msi, tmp_path):
    assert msi.export_unified_database(str(tmp_path / "empty")) is None
    msi.ssri_data = [{"name": "a", "company": "IOCL", "state": "Goa", "city": "x", "latitude": 1.0, "longitude": 2.0, "address": "ad"},
                     {"name": "b", "company": "IOCL", "state": "Goa", "city": "y"}]
    msi.bpcl_data = [{"name": "c", "company": "BPCL", "state": "Kerala", "city": "z", "latitude": 5.0, "longitude": 6.0, "customer_code": "C"}]
    msi.integrate_databases()
    out = tmp_path / "o"
    msi.export_unified_database(str(out))
    summ = json.loads(next(out.glob("unified_pumps_summary_*.json")).read_text())
    assert summ["total_unique_pumps"] == 3 and summ["unique_states"] == 2 and summ["unique_companies"] == 2
    assert summ["company_distribution"] == {"IOCL": 2, "BPCL": 1}
    assert summ["top_states"] == {"Goa": 2, "Kerala": 1}
    assert summ["data_quality"] == {"records_with_coordinates": 2, "records_with_address": 1, "records_with_customer_code": 1}
    assert summ["source_breakdown"] == {"SSRI API": 2, "BPCL Official": 1, "PPAC Reference": 0}
    gj = json.loads(next(out.glob("*.geojson")).read_text())
    assert [f["geometry"]["coordinates"] for f in gj["features"]] == [[2.0, 1.0], [6.0, 5.0]]
    assert len(list(out.glob("unified_pumps_*.csv"))) == 1


def test_top_states_truncates(msi):
    msi.unified_database = [{"state": f"S{i}"} for i in range(12)] + [{"state": "S0"}]
    top = msi._get_top_states(3)
    assert list(top)[0] == "S0" and len(top) == 3 and top["S0"] == 2


def test_run_integration_pipeline(msi, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert msi.run_integration(str(tmp_path / "no.json"), "b", "p") is False        # SSRI is mandatory
    j = tmp_path / "s.json"
    j.write_text(json.dumps([{"name": "a", "company": "IOCL", "state": "Goa", "city": "x", "latitude": 1.0, "longitude": 2.0}]))
    assert ims.MultiSourceDatabaseIntegrator().run_integration(str(j), "missing.csv", "missing.xlsx") is True
    assert list((tmp_path / "unified_petrol_pump_database").glob("unified_pumps_*.csv"))


def test_ims_main(monkeypatch):
    seen = {}
    monkeypatch.setattr(ims.MultiSourceDatabaseIntegrator, "run_integration",
                        lambda self, a, b, c: seen.update(a=a, b=b, c=c) or True)
    ims.main()
    assert seen["a"].endswith("ssri_all_pumps_20260624_063249.json") and seen["c"].endswith(".xls")
