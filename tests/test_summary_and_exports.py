"""create_comprehensive_retail_summary, generate_ppac_comparison_excel, integration, kaggle_loader,
progress_monitor. Offline: data is injected into the objects or written under tmp_path; the
hard-coded /Users/... inputs are made unreachable so the suite behaves the same on any machine."""
import json
import os

import pandas as pd
import pytest

import create_comprehensive_retail_summary as ccrs
import generate_ppac_comparison_excel as gpce
import integration
import kaggle_loader
import progress_monitor as pm

PUMPS = [
    {"state": "Kerala", "company": "IOCL", "has_petrol": True, "has_diesel": True, "has_cng": True, "petrol_price": 100.0},
    {"state": "Kerala", "company": "BPCL", "has_petrol": True, "has_diesel": True, "has_cng": False, "petrol_price": 0},
    {"state": "Goa", "company": "IOCL", "has_petrol": True, "has_diesel": False, "has_cng": False, "petrol_price": 99.0},
    {"state": "Goa", "company": "Shell", "has_petrol": False, "has_diesel": True, "has_cng": True, "petrol_price": 101.0},
]


@pytest.fixture
def no_hardcoded_inputs(monkeypatch, tmp_path):
    """Make every absolute /Users/... input unreachable and keep relative writes in tmp_path."""
    real_open = open

    def guarded_open(path, *a, **k):
        if str(path).startswith("/Users/"):
            raise FileNotFoundError(path)
        return real_open(path, *a, **k)

    def deny(*a, **k):
        raise FileNotFoundError("blocked")

    monkeypatch.setattr(ccrs, "open", guarded_open, raising=False)
    monkeypatch.setattr(pd, "read_csv", deny)
    monkeypatch.setattr(pd, "read_excel", deny)
    monkeypatch.chdir(tmp_path)


# ------------------------------------------------------------------ create_comprehensive_retail_summary
@pytest.fixture
def summ():
    s = ccrs.RetailOutletsSummary()
    s.ssri_data = [dict(p) for p in PUMPS]
    s.bpcl_data = pd.DataFrame({"state": ["kerala", "Goa", "Goa"], "name": list("abc")})
    s.cashatpos_data = pd.DataFrame({"state": ["Kerala"], "name": ["x"]})
    return s


def test_load_all_data_missing_files_yield_empty_sources(no_hardcoded_inputs, capsys):
    s = ccrs.RetailOutletsSummary()
    s.load_all_data()
    assert s.ssri_data == [] and s.bpcl_data.empty and s.cashatpos_data.empty and s.ppac_data.empty
    assert capsys.readouterr().out.count("not found") == 4


def test_summary_sheet_uses_loaded_counts_or_documented_defaults(summ):
    df = summ.create_summary_sheet()
    assert list(df["Data Source"])[-1] == "TOTAL POTENTIAL"
    assert list(df["Total Records"])[1:3] == [3, 1]
    summ.bpcl_data, summ.cashatpos_data = pd.DataFrame(), pd.DataFrame()
    assert list(summ.create_summary_sheet()["Total Records"])[1:3] == [161, 693]
    assert list(df["Total Records"])[0] == 107380 and list(df["Total Records"])[3] == 79417


def test_ssri_analysis_counts_and_percentages(summ):
    v = dict(zip(*[summ.create_ssri_analysis()[c] for c in ("Metric", "Value")]))
    assert v["Total Pumps"] == "4" and v["States Covered"] == "2" and v["Companies"] == "3"
    assert v["With CNG"] == "2 (50.0%)"
    assert v["With Fuel Prices"] == "3 (75.0%)"          # price 0 does not count (3 of 4 carry a price)
    summ.ssri_data = []
    assert summ.create_ssri_analysis().empty


def test_state_comparison_merges_sources_case_insensitively(summ):
    df = summ.create_state_comparison().set_index("State")
    assert df.loc["KERALA", ["SSRI Pumps", "BPCL Dealers", "Cash@PoS Stations", "Total Outlets"]].tolist() == [2, 1, 1, 4]
    assert df.loc["GOA", "Total Outlets"] == 4
    assert list(df.index)[0] in ("KERALA", "GOA")
    summ.ssri_data = []
    assert summ.create_state_comparison().empty


def test_state_comparison_sorted_descending(summ):
    summ.ssri_data.append({"state": "Goa", "company": "x"})
    t = summ.create_state_comparison()["Total Outlets"].tolist()
    assert t == sorted(t, reverse=True) and t[0] == 5


def test_company_analysis_share_bar(summ):
    df = summ.create_company_analysis()
    assert list(df["Company"])[0] == "IOCL" and df.loc[0, "Pump Count"] == 2
    assert df.loc[0, "% of Total"] == "50.0%"
    assert df.loc[0, "Market Share"] == "█" * 10 + "░" * 10          # 50% / 5 = 10 filled of 20
    assert all(len(b) == 20 for b in df["Market Share"])
    summ.ssri_data = []
    assert summ.create_company_analysis().empty


def test_fuel_analysis_counts(summ):
    df = summ.create_fuel_analysis()
    assert df["Stations"].tolist() == [3, 3, 2, 1]
    assert df["% of Total"].tolist() == ["75.0%", "75.0%", "50.0%", "25.0%"]
    summ.ssri_data = []
    assert summ.create_fuel_analysis().empty


def test_export_to_excel_writes_every_sheet(summ, tmp_path, capsys):
    out = tmp_path / "s.xlsx"
    summ.export_to_excel(str(out))
    xl = pd.ExcelFile(out)
    assert xl.sheet_names == ["SUMMARY", "SSRI Analysis", "State Comparison", "Company Analysis",
                              "Fuel Availability", "BPCL Dealers", "Cash@PoS Stations"]
    summ.ssri_data, summ.bpcl_data, summ.cashatpos_data = [], pd.DataFrame(), pd.DataFrame()
    out2 = tmp_path / "s2.xlsx"
    summ.export_to_excel(str(out2))
    assert pd.ExcelFile(out2).sheet_names == ["SUMMARY"]


def test_run_and_main_write_timestamped_workbook(no_hardcoded_inputs, tmp_path, capsys):
    ccrs.main()
    files = list(tmp_path.glob("RETAIL_OUTLETS_SUMMARY_*.xlsx"))
    assert len(files) == 1
    assert "SUMMARY COMPLETE" in capsys.readouterr().out


# ------------------------------------------------------------------ generate_ppac_comparison_excel
def make_ppac(tmp_path, rows, header_row=7, count_col="1.10.2021 (P)"):
    """Excel laid out like the PPAC file: 7 metadata rows, then the header, then data."""
    meta = [["meta"] + [None] * 2 for _ in range(header_row)]
    body = [["State/UT", "IOCL", count_col]] + rows
    path = tmp_path / "ppac.xlsx"
    pd.DataFrame(meta + body).to_excel(path, header=False, index=False)
    return path


@pytest.fixture
def cmp_(tmp_path):
    ssri = tmp_path / "ssri.json"
    ssri.write_text(json.dumps([
        {"name": "p1", "state": "Kerala", "city": "K", "company": "IOCL", "latitude": 1, "longitude": 2, "address": "a", "phone": "1"},
        {"name": "p2", "state": "Kerala", "city": "K", "company": "IOCL", "latitude": 1, "longitude": 2, "address": "a", "phone": "1"},
        {"name": "p3", "state": "Goa", "city": "G", "company": "Acme", "latitude": 1, "longitude": 2, "address": "a", "phone": "1"},
        {"name": "p4", "state": "Assam", "city": "G", "company": "Unknown", "latitude": 1, "longitude": 2, "address": "a", "phone": "1"},
    ]))
    ppac = make_ppac(tmp_path, [["kerala ", 10, 4.0], ["Goa", 5, 40.0], ["Region North", 1, None], ["Bihar", 2, 8.0]])
    c = gpce.PPACComparison(str(ssri), str(ppac))
    c.load_ssri_data()
    return c


def test_load_ppac_normalises_state_and_drops_region_rows(cmp_):
    assert cmp_.load_ppac_data() is True
    # the loader upper-cases only when the column dtype is `object` (pandas<3); downstream code re-normalises,
    # so assert on the normalised view, which is the same on every pandas
    assert [str(s).strip().upper() for s in cmp_.ppac_data["State"]] == ["KERALA", "GOA", "BIHAR"]
    assert list(cmp_.ppac_data["Count"]) == [4.0, 40.0, 8.0]


def test_load_ppac_failure_is_reported_not_raised(tmp_path, capsys):
    c = gpce.PPACComparison("x.json", str(tmp_path / "missing.xlsx"))
    assert c.load_ppac_data() is False
    assert "Error loading PPAC" in capsys.readouterr().out and c.ppac_data is None


def test_load_ppac_falls_back_to_last_numeric_column(tmp_path):
    c = gpce.PPACComparison("x", str(make_ppac(tmp_path, [["Kerala", 10, 4.0]], count_col="Total 2021")))
    assert c.load_ppac_data() is True
    assert list(c.ppac_data["Count"]) == [4.0]


def test_state_comparison_coverage_bands(cmp_):
    cmp_.load_ppac_data()
    cmp_.ssri_pumps = (
        [{"state": "A"}] * 75 + [{"state": "B"}] * 50 + [{"state": "C"}] * 25 + [{"state": "D"}] * 1 + [{"state": "NOPPAC"}] * 3)
    cmp_.ppac_data = pd.DataFrame({"State": ["A", "B", "C", "D", "E", "F"], "Count": [100, 100, 100, 100, 100, 0]})
    df = cmp_.create_state_comparison().set_index("State")
    assert df.loc["A", "Coverage_Level"] == "EXCELLENT" and df.loc["A", "Coverage_%"] == 75.0     # >= 75 inclusive
    assert df.loc["B", "Coverage_Level"] == "GOOD"                                                 # >= 50
    assert df.loc["C", "Coverage_Level"] == "MODERATE"                                             # >= 25
    assert df.loc["D", "Coverage_Level"] == "LIMITED" and df.loc["E", "Coverage_Level"] == "NONE"
    assert df.loc["NOPPAC", "Coverage_%"] == 100 and df.loc["NOPPAC", "Coverage_Level"] == "EXCELLENT"
    assert df.loc["F", "Coverage_%"] == 0 and df.loc["F", "Difference"] == 0
    assert df.loc["A", "Difference"] == -25
    assert df.index[0] == "A"                                                                      # sorted by SSRI_Count


def test_state_comparison_skips_non_numeric_counts_and_bad_columns(cmp_, capsys):
    cmp_.ppac_data = pd.DataFrame({"State": ["A", "B"], "Count": ["n/a", float("inf")]})
    cmp_.ssri_pumps = [{"state": "a"}]
    df = cmp_.create_state_comparison()
    assert df.loc[df["State"] == "A", "PPAC_Count"].iloc[0] == 0
    cmp_.ppac_data = pd.DataFrame({"Other": [1]})
    cmp_.create_state_comparison()
    assert "columns not as expected" in capsys.readouterr().out
    cmp_.ppac_data = None
    assert len(cmp_.create_state_comparison()) == 1


def test_company_comparison_descriptions_and_percentages(cmp_):
    df = cmp_.create_company_comparison()
    assert df.iloc[0].to_dict() == {"Company": "IOCL", "SSRI_Count": 2, "SSRI_Percent_%": 50.0,
                                    "Description": "Indian Oil Corporation Limited"}
    assert df.set_index("Company").loc["Acme", "Description"] == "Operator: Acme"
    assert df.set_index("Company").loc["Unknown", "Description"] == "Unclassified/Other Operators"


def test_outlets_sheet_column_order_and_serial(cmp_):
    df = cmp_.create_outlets_sheet()
    assert list(df.columns) == ["S.No", "Pump_Name", "State", "City", "Company", "Latitude", "Longitude", "Address", "Phone"]
    assert list(df["S.No"]) == [1, 2, 3, 4]


def test_summary_sheet_metrics(cmp_):
    cmp_.load_ppac_data()
    st, co = cmp_.create_state_comparison(), cmp_.create_company_comparison()
    v = dict(zip(*[cmp_.create_summary_sheet(st, co)[c] for c in ("Metric", "Value")]))
    assert v["Total SSRI Pumps Extracted"] == 4 and v["Total PPAC Outlets (Oct 2021)"] == 52
    assert v["Overall Coverage %"] == f"{4 / 52 * 100:.2f}%"
    assert v["States Covered by SSRI"] == 3 and v["States Covered by PPAC"] == 3 and v["States Covered by Both"] == 2
    assert v["Top Company"] == "IOCL" and v["Top Company Share %"] == "50.00%"


def test_summary_sheet_without_ppac_data_is_a_known_crash(cmp_):
    st, co = cmp_.create_state_comparison(), cmp_.create_company_comparison()
    assert cmp_.ppac_data is None
    with pytest.raises(AttributeError):
        cmp_.create_summary_sheet(st, co)


@pytest.mark.xfail(strict=True, raises=AttributeError,
                   reason="create_summary_sheet() reads self.ppac_data.columns in its fallback loop even "
                          "when ppac_data is None (PPAC load failed), so a failed PPAC load crashes the "
                          "report instead of printing a summary with total_ppac = 0")
def test_summary_sheet_survives_failed_ppac_load(cmp_):
    st, co = cmp_.create_state_comparison(), cmp_.create_company_comparison()
    cmp_.create_summary_sheet(st, co)


def test_generate_excel_report_end_to_end(cmp_, tmp_path):
    out = tmp_path / "r.xlsx"
    cmp_.generate_excel_report(str(out))
    assert pd.ExcelFile(out).sheet_names == ["SUMMARY", "STATE_COMPARISON", "COMPANY_ANALYSIS", "EXTRACTED_OUTLETS"]


def test_gpce_main_with_missing_inputs_raises_file_not_found(monkeypatch):
    real_open = open

    def deny(path, *a, **k):
        if str(path).startswith("/Users/"):
            raise FileNotFoundError(path)
        return real_open(path, *a, **k)

    monkeypatch.setattr(gpce, "open", deny, raising=False)
    with pytest.raises(FileNotFoundError):
        gpce.main()


# ------------------------------------------------------------------ integration (SSR API client)
class Resp:
    def __init__(self, status=200, payload=None, bad_json=False):
        self.status_code, self._p, self._bad = status, payload, bad_json

    def json(self):
        if self._bad:
            raise json.JSONDecodeError("x", "y", 0)
        return self._p


def test_fetch_from_api_endpoint_selection_and_failure_modes(monkeypatch):
    seen = {}

    def fake_get(url, headers=None, timeout=None):
        seen["url"], seen["timeout"] = url, timeout
        return seen["resp"]

    monkeypatch.setattr(integration.requests, "get", fake_get)
    o = integration.OutletAPIIntegration()
    seen["resp"] = Resp(200, [{"a": 1}])
    assert o.fetch_from_api("outlets") == [{"a": 1}]
    assert seen["url"] == "https://api.ssrinnovationlab.com/api/outlets/" and seen["timeout"] == 10
    o.fetch_from_api("bogus")
    assert seen["url"].endswith("/api/test/18/")                      # unknown endpoint falls back to 'test'
    seen["resp"] = Resp(404, None)
    assert o.fetch_from_api() is None
    seen["resp"] = Resp(200, bad_json=True)
    assert o.fetch_from_api() is None

    def boom(*a, **k):
        raise integration.requests.exceptions.ConnectionError("down")
    monkeypatch.setattr(integration.requests, "get", boom)
    assert o.fetch_from_api() is None


def test_process_outlet_data_standardises_columns():
    o = integration.OutletAPIIntegration()
    assert o.process_outlet_data([]) is None and o.process_outlet_data(None) is None
    df = o.process_outlet_data([{"name": "A", "lat": "12.5", "lng": "bad", "type": "retail"}])
    assert {"outlet_name", "latitude", "longitude", "city", "state", "outlet_type"} <= set(df.columns)
    assert df.loc[0, "latitude"] == 12.5 and pd.isna(df.loc[0, "longitude"])       # bad numeric -> NaN
    assert df.loc[0, "city"] is None


def test_merge_with_existing_dedups_on_coords_and_name(tmp_path):
    o = integration.OutletAPIIntegration()
    api = pd.DataFrame({"outlet_name": ["A"], "latitude": [1.0], "longitude": [2.0]})
    assert o.merge_with_existing(None) is None
    assert len(o.merge_with_existing(api, str(tmp_path / "missing.csv"))) == 1
    existing = tmp_path / "e.csv"
    pd.DataFrame({"outlet_name": ["A", "B"], "latitude": [1.0, 1.0], "longitude": [2.0, 2.0]}).to_csv(existing, index=False)
    merged = o.merge_with_existing(api, str(existing))
    assert list(merged["outlet_name"]) == ["A", "B"]                  # same coords but different name kept; exact dup dropped
    bad = tmp_path / "bad.csv"
    bad.write_text("")
    assert len(o.merge_with_existing(api, str(bad))) == 1             # unreadable existing file -> API data only


def test_export_to_formats_writes_all_artifacts(tmp_path):
    o = integration.OutletAPIIntegration()
    df = pd.DataFrame({"outlet_name": ["A", "B"], "latitude": [1.0, None], "longitude": [2.0, 3.0],
                       "city": ["c", "c"], "state": ["s", "t"], "company": ["x", "x"]})
    out = tmp_path / "o"
    o.export_to_formats(df, str(out))
    names = sorted(p.suffix for p in out.iterdir())
    assert names.count(".csv") == 1 and names.count(".geojson") == 1 and names.count(".json") == 2
    gj = json.loads(next(out.glob("*.geojson")).read_text())
    assert len(gj["features"]) == 1 and gj["features"][0]["geometry"]["coordinates"] == [2.0, 1.0]   # [lng, lat]
    stats = json.loads(next(out.glob("outlets_stats_*.json")).read_text())
    assert stats["total_outlets"] == 2 and stats["with_coordinates"] == 1 and stats["states"] == 2
    empty = tmp_path / "e"
    o.export_to_formats(pd.DataFrame(), str(empty))
    o.export_to_formats(None, str(empty))
    assert list(empty.iterdir()) == []


def test_export_to_formats_swallows_write_errors(tmp_path, capsys):
    o = integration.OutletAPIIntegration()
    o.export_to_formats(pd.DataFrame({"x": [1]}), str(tmp_path / "o"))        # no lat/lon columns -> KeyError inside
    assert "o" in os.listdir(tmp_path)


def test_integration_main_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(integration.requests, "get", lambda *a, **k: Resp(200, [{"name": "A", "lat": 1, "lng": 2}]))
    integration.main()
    assert any((tmp_path / "outlet_data").glob("outlets_*.csv"))
    monkeypatch.setattr(integration.requests, "get", lambda *a, **k: Resp(500))
    integration.main()


# ------------------------------------------------------------------ kaggle_loader
def test_kaggle_load_maps_columns_and_skips_bad_rows(tmp_path):
    p = tmp_path / "k.csv"
    pd.DataFrame({"Outlet Name": ["A", "B", "C", "D"], "Latitude": [1.0, None, "x", 4.0],
                  "Longitude": [2.0, 2.0, 3.0, 5.0], "State": ["S", "S", "T", "S"], "City": ["c1", "c1", "c2", "c3"],
                  "Operator": ["IOCL", "BPCL", "Shell", "Q"]}).to_csv(p, index=False)
    k = kaggle_loader.KaggleDatasetLoader()
    out = k.load_from_csv(str(p))
    assert [o["name"] for o in out] == ["A", "D"]                    # NaN lat skipped; 'x' lat skipped (ValueError)
    assert out[0] == {"name": "A", "latitude": 1.0, "longitude": 2.0, "source": "Kaggle", "company": "IOCL",
                      "city": "c1", "state": "S"}
    assert k.stats == {"total": 2, "with_coords": 2, "states": 1, "cities": 2, "companies": 2}


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="a blank city/operator cell is NaN and str(NaN) == 'nan', which then counts as a real "
                          "city and a real company in the stats and exports (kaggle_loader.py load_from_csv)")
def test_kaggle_blank_cells_do_not_become_the_string_nan(tmp_path):
    p = tmp_path / "k.csv"
    p.write_text("name,latitude,longitude,city,company\nA,1,2,,\n")
    k = kaggle_loader.KaggleDatasetLoader()
    out = k.load_from_csv(str(p))
    assert out[0]["city"] != "nan" and out[0]["company"] != "nan"


def test_kaggle_missing_or_unreadable_csv(tmp_path):
    k = kaggle_loader.KaggleDatasetLoader()
    assert k.load_from_csv(str(tmp_path / "nope.csv")) == []
    bad = tmp_path / "bad.csv"
    bad.write_bytes(b"")
    assert k.load_from_csv(str(bad)) == []


def test_kaggle_export_all_formats(tmp_path, capsys):
    k = kaggle_loader.KaggleDatasetLoader()
    assert k.export_all_formats(str(tmp_path / "x")) is None          # nothing loaded -> nothing written
    k.outlets = [{"name": "A", "latitude": 1.0, "longitude": 2.0, "company": "c", "city": "ci", "state": "st", "source": "Kaggle"},
                 {"name": "Z", "latitude": 0.0, "longitude": 0.0, "company": "c", "city": "ci", "state": "st", "source": "Kaggle"},
                 {"name": "Y", "latitude": 0.0, "longitude": 5.0, "company": "c", "city": "ci", "state": "st", "source": "Kaggle"},
                 {"name": "X", "latitude": 5.0, "longitude": 0.0, "company": "c", "city": "ci", "state": "st", "source": "Kaggle"}]
    k.stats.update(states=1, cities=1, companies=1)
    out = tmp_path / "out"
    assert k.export_all_formats(str(out)) == str(out)
    gj = json.loads(next(out.glob("*.geojson")).read_text())
    assert len(gj["features"]) == 1                                   # a lat OR lng of exactly 0 is falsy and the outlet dropped
    js = next(out.glob("*.js")).read_text()
    assert "const FUEL_PUMP_LOCATIONS = [" in js and "total: 4," in js
    k.print_summary()
    assert capsys.readouterr().out


def test_kaggle_main(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["k"])
    kaggle_loader.main()                                               # no CSV found anywhere
    (tmp_path / "outlets.csv").write_text("name,latitude,longitude\nA,1,2\n")
    kaggle_loader.main()
    assert any((tmp_path / "outlet_data_kaggle").glob("kaggle_outlets_*.csv"))
    monkeypatch.setattr("sys.argv", ["k", str(tmp_path / "missing.csv")])
    kaggle_loader.main()


# ------------------------------------------------------------------ progress_monitor
LOG = ("SSRI SYSTEMATIC EXTRACTION\ntotal unique: 100\ntotal unique: 250\nPagination complete: 1200 pumps\n"
       "Company extraction complete: 300\n")


@pytest.fixture
def mon(tmp_path):
    return pm.ProgressMonitor(str(tmp_path / "log.txt"))


def test_read_log_missing_and_unreadable(mon, tmp_path):
    assert mon.read_log() == ""
    (tmp_path / "log.txt").write_bytes(b"\xff\xfe\x00bad")
    assert mon.read_log() == ""                                        # undecodable -> empty
    (tmp_path / "log.txt").write_text("ok")
    assert mon.read_log() == "ok"


def test_parse_log_stages_and_counts(mon):
    mon.parse_log("")
    assert not any(s["completed"] for s in mon.stages.values()) and mon.start_time is None
    mon.parse_log(LOG)
    assert mon.start_time is not None and mon.total_pumps == 250       # last 'total unique' wins
    assert mon.stages["pagination"] == {"weight": 40, "completed": True, "count": 1200}
    assert mon.stages["company"]["count"] == 300 and not mon.stages["city"]["completed"]
    t0 = mon.start_time
    mon.parse_log(LOG + "City extraction complete: 40\nNearby extraction complete: 5\nExport complete\n")
    assert mon.start_time == t0                                        # start time set once
    assert mon.stages["city"]["count"] == 40 and mon.stages["nearby"]["count"] == 5
    assert mon.stages["export"] == {"weight": 5, "completed": True, "count": 1}


def test_progress_is_weighted_and_truncated(mon):
    assert mon.calculate_progress() == 0
    mon.stages["pagination"]["completed"] = True
    assert mon.calculate_progress() == 40
    mon.stages["company"]["completed"] = True
    mon.stages["city"]["completed"] = True
    assert mon.calculate_progress() == 85
    for s in mon.stages.values():
        s["completed"] = True
    assert mon.calculate_progress() == 100
    for s in mon.stages.values():
        s["weight"] = 0
    assert mon.calculate_progress() == 0


def test_progress_bar_and_elapsed(mon):
    assert mon.draw_progress_bar(50, width=10) == "[" + "█" * 5 + "░" * 5 + "] 50%"
    assert mon.draw_progress_bar(0, 4) == "[░░░░] 0%" and mon.draw_progress_bar(100, 4) == "[████] 100%"
    assert mon.get_elapsed_time() == "00:00"
    from datetime import datetime, timedelta
    mon.start_time = datetime.now() - timedelta(seconds=125)
    assert mon.get_elapsed_time() == "02:05"


def test_current_stage_walks_the_pipeline(mon):
    assert "Initializing" in mon.get_current_stage()
    mon.stages["pagination"]["completed"] = True
    assert "Company" in mon.get_current_stage()
    mon.stages["company"]["completed"] = True
    assert "City" in mon.get_current_stage()
    mon.stages["city"]["completed"] = True
    assert "Nearby" in mon.get_current_stage()
    mon.stages["nearby"]["completed"] = True
    assert "Exporting" in mon.get_current_stage()


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="once every stage (incl. export) is complete get_current_stage() falls through to "
                          "its final `elif pagination completed` branch and reports 'Fetching by Pagination'")
def test_current_stage_when_everything_done(mon):
    for s in mon.stages.values():
        s["completed"] = True
    assert "Pagination" not in mon.get_current_stage()


def test_display_and_run(mon, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(pm.os, "system", lambda c: 0)
    monkeypatch.setattr(pm.time, "sleep", lambda s: None)
    assert mon.display() is False
    mon.parse_log(LOG)
    assert mon.display() is False
    for s in mon.stages.values():
        s["completed"] = True
    assert mon.display() is True
    log = tmp_path / "log.txt"
    log.write_text(LOG + "City extraction complete: 1\nNearby extraction complete: 1\nExport complete\n")
    m2 = pm.ProgressMonitor(str(log))
    m2.run(update_interval=0)                                          # one pass reaches 100% and stops
    assert m2.calculate_progress() == 100


def test_run_stops_on_keyboard_interrupt(mon, monkeypatch, capsys):
    monkeypatch.setattr(pm.os, "system", lambda c: 0)
    calls = {"n": 0}

    def sleeper(s):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt
    monkeypatch.setattr(pm.time, "sleep", sleeper)
    mon.run(update_interval=0)
    assert calls["n"] == 2


def test_progress_main_runs_monitor(monkeypatch):
    seen = {}
    monkeypatch.setattr(pm.ProgressMonitor, "run", lambda self, update_interval=2: seen.update(i=update_interval, f=self.log_file))
    pm.main()
    assert seen["i"] == 2 and seen["f"].endswith("extraction_progress.log")
