"""ssri_petrol_pumps_api.SSRIPetrolPumpsAPI against a fake `requests.get`."""
import json

import pytest

import ssri_petrol_pumps_api as sp


class Resp:
    def __init__(self, code=200, payload=None):
        self.status_code, self.payload = code, payload

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


@pytest.fixture
def api():
    return sp.SSRIPetrolPumpsAPI()


def fake(monkeypatch, resp, record=None):
    def get(url, params=None, timeout=None, headers=None):
        if record is not None:
            record.append((url, params, timeout, headers))
        if isinstance(resp, BaseException):
            raise resp
        return resp
    monkeypatch.setattr(sp.requests, "get", get)


@pytest.mark.parametrize("payload,expected", [
    ([{"a": 1}], [{"a": 1}]),
    ({"results": [{"a": 2}]}, [{"a": 2}]),
    ({"data": [{"a": 3}]}, [{"a": 3}]),
    ({"pumps": [{"a": 4}]}, [{"a": 4}]),
    ({}, []),
    ("text", []),
])
def test_fetch_all_pumps_response_shapes(api, monkeypatch, payload, expected):
    fake(monkeypatch, Resp(200, payload))
    assert api.fetch_all_pumps() == expected


def test_fetch_all_pumps_request_and_failures(api, monkeypatch):
    rec = []
    fake(monkeypatch, Resp(200, []), rec)
    api.fetch_all_pumps(limit=5, page=3)
    assert rec[0][0].endswith("/api/petrol-pumps/pumps/") and rec[0][1] == {"limit": 5, "page": 3}
    assert rec[0][2] == 30 and rec[0][3] == {"Accept": "application/json"}
    fake(monkeypatch, Resp(500))
    assert api.fetch_all_pumps() == []
    fake(monkeypatch, Resp(200, json.JSONDecodeError("x", "y", 0)))
    assert api.fetch_all_pumps() == []
    fake(monkeypatch, RuntimeError("down"))
    assert api.fetch_all_pumps() == []


@pytest.mark.parametrize("method,args,suffix,param", [
    ("fetch_by_city", ("Pune",), "/by-city/", {"city": "Pune"}),
    ("fetch_by_company", ("IOCL",), "/by-company/", {"company": "IOCL"}),
    ("fetch_nearby", (10.0, 20.0), "/nearby/", {"latitude": 10.0, "longitude": 20.0, "radius": 5}),
])
def test_filtered_fetchers(api, monkeypatch, method, args, suffix, param):
    rec = []
    fake(monkeypatch, Resp(200, {"results": [{"x": 1}]}), rec)
    assert getattr(api, method)(*args) == [{"x": 1}]
    assert rec[0][0].endswith(suffix) and rec[0][1] == param
    fake(monkeypatch, Resp(200, [{"y": 2}]))
    assert getattr(api, method)(*args) == [{"y": 2}]
    fake(monkeypatch, Resp(404))
    assert getattr(api, method)(*args) == []
    fake(monkeypatch, RuntimeError("x"))
    assert getattr(api, method)(*args) == []


def test_nearby_radius_override(api, monkeypatch):
    rec = []
    fake(monkeypatch, Resp(200, []), rec)
    api.fetch_nearby(1.0, 2.0, radius=25)
    assert rec[0][1]["radius"] == 25


def test_process_pumps_standardises_and_counts(api):
    out = api.process_pumps([
        {"pump_name": "A", "lat": "10.5", "lng": "20.5", "location": "Pune", "state": "MH", "brand": "IOCL", "phone": "1"},
        {"name": "B", "latitude": 11, "longitude": 21},
        {"name": "NoGPS", "latitude": 0, "longitude": 5},
        {"name": "Bad", "latitude": "x", "longitude": 5},
    ])
    assert [p["name"] for p in out] == ["A", "B"]
    assert out[0] == {"name": "A", "latitude": 10.5, "longitude": 20.5, "city": "Pune", "state": "MH",
                      "company": "IOCL", "address": "", "phone": "1", "fuel_types": []}
    assert out[1]["city"] == "Unknown" and out[1]["company"] == "Unknown"
    assert api.stats["total"] == 2 and api.stats["states"] == {"MH": 1, "Unknown": 1}


def test_process_pumps_bad_record_is_skipped(api):
    assert api.process_pumps([None, {"name": "ok", "latitude": 1, "longitude": 2}])[0]["name"] == "ok"
    assert api.stats["total"] == 1


def test_safe_float(api):
    assert api._safe_float("1.5") == 1.5 and api._safe_float(None) is None
    assert api._safe_float(0) is None and api._safe_float("x") is None and api._safe_float([]) is None


def test_export_data(api, tmp_path):
    assert api.export_data([], str(tmp_path / "none")) is None
    pumps = api.process_pumps([{"name": "A", "latitude": 10.5, "longitude": 20.5, "state": "MH", "city": "Pune", "company": "IOCL"}])
    out = tmp_path / "o"
    assert api.export_data(pumps, str(out)) == str(out)
    gj = json.loads(next(out.glob("*.geojson")).read_text())
    assert gj["features"][0]["geometry"]["coordinates"] == [20.5, 10.5]
    js = next(out.glob("*.js")).read_text()
    assert "total: 1," in js and "states: 1," in js
    sw = json.loads(next(out.glob("*state_wise*.json")).read_text())
    assert sw["total_pumps"] == 1 and sw["states"] == {"MH": 1} and sw["companies"] == {"IOCL": 1}
    assert api.export_data([{"name": "x"}], str(tmp_path / "bad")) is None        # missing keys -> swallowed
    api.print_summary()


def test_main_falls_back_to_company_queries(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    calls = []

    def get(url, params=None, timeout=None, headers=None):
        calls.append(url)
        if url.endswith("/pumps/"):
            return Resp(200, [])
        return Resp(200, [{"name": params["company"], "latitude": 1.0 + len(calls) / 100, "longitude": 2.0}])
    monkeypatch.setattr(sp.requests, "get", get)
    sp.main()
    assert sum(c.endswith("/by-company/") for c in calls) == 5
    assert list((tmp_path / "outlet_data_ssri_pumps").glob("ssri_pumps_*.csv"))


def test_main_primary_path_and_empty(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sp.requests, "get", lambda *a, **k: Resp(200, [{"name": "A", "latitude": 1, "longitude": 2}]))
    sp.main()
    assert (tmp_path / "outlet_data_ssri_pumps").exists()
    monkeypatch.setattr(sp.requests, "get", lambda *a, **k: Resp(200, [{"name": "A", "latitude": 0, "longitude": 0}]))
    sp.main()                                                                       # nothing processable
    monkeypatch.setattr(sp.requests, "get", lambda *a, **k: Resp(500))
    sp.main()
