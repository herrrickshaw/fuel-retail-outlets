"""ssri_systematic_extractor.SSRISystematicExtractor against a scripted fake `requests.get`."""
import json

import pytest

import ssri_systematic_extractor as se


class Resp:
    def __init__(self, code=200, payload=None):
        self.status_code, self.payload = code, payload

    def json(self):
        return self.payload


class Net:
    def __init__(self, script):
        self.script, self.calls = script, []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {}), timeout))
        if callable(self.script):
            return self.script(url, params)
        item = self.script[min(len(self.calls) - 1, len(self.script) - 1)]
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture
def sleeps(monkeypatch):
    s = []
    monkeypatch.setattr(se.time, "sleep", lambda x: s.append(x))
    return s


@pytest.fixture
def ex():
    return se.SSRISystematicExtractor()


def p(i, **kw):
    d = {"name": f"Pump{i}", "latitude": 10.0 + i * 0.01, "longitude": 20.0, "state": "Goa", "company": "IOCL", "city": "Panaji"}
    d.update(kw)
    return d


def test_add_pumps_dedup_key_and_stats(ex):
    ex._add_pumps([p(1), p(1), {"name": "no gps"}, p(2, lat=None, state=None, brand="Shell", company=None, location="Vasco", city=None)], "city")
    assert len(ex.all_pumps) == 2 and ex.stats["total_fetched"] == 2 and ex.stats["total_unique"] == 2
    assert ex.stats["sources"]["city"] == 2 and ex.stats["states"] == {"Goa": 1, "Unknown": 1}
    rec = next(r for r in ex.all_pumps.values() if r["name"] == "Pump2")
    assert (rec["state"], rec["company"], rec["city"]) == ("Unknown", "Shell", "Vasco")
    assert "10.0100_20.0000_Pump1" in ex.all_pumps                          # 4-decimal + first 20 chars of name


def test_dedup_key_resolution_is_four_decimals_and_name_prefix(ex):
    ex._add_pumps([p(0, latitude=10.00001), p(0, latitude=10.00004)], "pagination")                 # same 4dp, same name
    assert len(ex.all_pumps) == 1
    ex._add_pumps([p(0, latitude=10.0001)], "pagination")                                           # next 4dp cell
    ex._add_pumps([p(0, name="A" * 25), p(0, name="A" * 20 + "ZZZZZ")], "pagination")               # names equal in first 20 chars
    assert len(ex.all_pumps) == 3


@pytest.mark.xfail(strict=True, raises=ValueError,
                   reason="_add_pumps() formats the dedup key with f'{lat:.4f}' before any float() conversion, so "
                          "string coordinates (which the sibling extractors explicitly coerce with float()) raise "
                          "ValueError and the whole page is lost")
def test_add_pumps_accepts_string_coordinates(ex):
    ex._add_pumps([{"name": "x", "latitude": "15.5", "longitude": "73.8"}], "pagination")
    assert len(ex.all_pumps) == 1


def test_safe_float(ex):
    assert ex._safe_float("2.5") == 2.5 and ex._safe_float(0) is None and ex._safe_float(None) is None
    assert ex._safe_float("x") is None


def test_pagination_stops_after_three_consecutive_empties(ex, monkeypatch, sleeps):
    net = Net([Resp(200, [p(1)]), Resp(200, {"results": [p(2)]}), Resp(200, {"data": [p(3)]}), Resp(200, [])])
    monkeypatch.setattr(se.requests, "get", net)
    ex.extract_by_pagination()
    assert len(net.calls) == 3 + 3 and len(ex.all_pumps) == 3 and ex.stats["sources"]["pagination"] == 3
    assert net.calls[0][1] == {"limit": 1000, "page": 1}


def test_pagination_non_200_and_exceptions(ex, monkeypatch, sleeps):
    net = Net([Resp(500)])
    monkeypatch.setattr(se.requests, "get", net)
    ex.extract_by_pagination()
    assert len(net.calls) == 3 and sleeps == [1, 1]
    e2 = se.SSRISystematicExtractor()
    net2 = Net([RuntimeError("x")])
    monkeypatch.setattr(se.requests, "get", net2)
    e2.extract_by_pagination(max_pages=4)
    assert len(net2.calls) == 4                                              # exceptions never trip the empty-page stop


def test_pagination_empty_counter_resets_on_data(ex, monkeypatch, sleeps):
    net = Net([Resp(200, []), Resp(200, []), Resp(200, [p(1)]), Resp(200, []), Resp(200, []), Resp(200, [p(2)])])
    monkeypatch.setattr(se.requests, "get", net)
    ex.extract_by_pagination(max_pages=6)
    assert len(net.calls) == 6 and len(ex.all_pumps) == 2


def test_company_city_nearby(ex, monkeypatch, sleeps):
    def script(url, params):
        if url.endswith("/by-company/"):
            return Resp(200, [p(ord(params["company"][0]))]) if params["company"] in ("IOCL", "Shell") else Resp(404)
        if url.endswith("/by-city/"):
            if params["city"] == "Pune":
                raise RuntimeError("down")
            return Resp(200, {"results": [p(1000 + ord(params["city"][0]))]}) if params["city"] == "Delhi" else Resp(200, [])
        return Resp(200, [p(5000)])
    monkeypatch.setattr(se.requests, "get", Net(script))
    ex.extract_by_company()
    assert ex.stats["sources"]["company"] == 2
    ex.extract_by_city()
    assert ex.stats["sources"]["city"] == 1
    ex.extract_by_nearby()
    assert ex.stats["sources"]["nearby"] == 1                                # same pump from every grid cell: de-duplicated
    ex.extract_by_city(["Mumbai"])
    ex.extract_by_nearby([(1.0, 2.0, "x")])


def test_nearby_uses_50km_radius(ex, monkeypatch, sleeps):
    net = Net([Resp(200, [])])
    monkeypatch.setattr(se.requests, "get", net)
    ex.extract_by_nearby([(10.0, 20.0, "c")])
    assert net.calls[0][1] == {"latitude": 10.0, "longitude": 20.0, "radius": 50}


def test_export_and_summary(ex, tmp_path, capsys):
    assert ex.export_data(str(tmp_path / "none")) is None
    ex._add_pumps([p(1), p(2, state="Kerala", company="BPCL"), p(3, latitude=0.0)], "company")
    out = tmp_path / "o"
    assert ex.export_data(str(out)) == str(out)
    gj = json.loads(next(out.glob("*.geojson")).read_text())
    assert len(gj["features"]) == 2 and gj["features"][0]["geometry"]["coordinates"] == [20.0, 10.01]
    s = json.loads(next(out.glob("*summary*.json")).read_text())
    assert s["total_pumps"] == 2 and s["unique_states"] == 2 and s["extraction_sources"]["company"] == 2
    assert "total: 2," in next(out.glob("*.js")).read_text()
    ex.print_final_summary()
    bad = se.SSRISystematicExtractor()
    bad.all_pumps = {"k": {"name": "x"}}                                      # missing keys -> swallowed
    assert bad.export_data(str(tmp_path / "bad")) is None


def test_full_run_and_main(monkeypatch, tmp_path, sleeps):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(se.requests, "get", Net([Resp(200, [p(1)])] * 1))
    se.main()
    assert list((tmp_path / "outlet_data_ssri_100k").glob("ssri_pumps_100k_*.csv"))
    monkeypatch.setattr(se.requests, "get", Net([Resp(404)]))
    assert se.SSRISystematicExtractor().run_full_extraction() is None
