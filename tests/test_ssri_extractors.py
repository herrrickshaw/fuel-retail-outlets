"""The three SSRI API extractors (complete / multi-strategy / 107k) against a scripted fake
`requests.get`: pagination stop rules, retry/back-off, GPS and id de-duplication, exports."""
import json

import pytest
import requests

import extract_all_ssri_complete as eac
import extract_all_ssri_pumps as eap
import extract_ssri_complete_107k as e107


class Resp:
    def __init__(self, code=200, payload=None):
        self.status_code, self._p = code, payload

    def json(self):
        if isinstance(self._p, Exception):
            raise self._p
        return self._p


class Net:
    """Scripted requests.get: a list (consumed in order, last item repeats) or a callable."""

    def __init__(self, script):
        self.script, self.calls = script, []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {}), timeout))
        if callable(self.script):
            return self.script(url, params)
        i = min(len(self.calls) - 1, len(self.script) - 1)
        item = self.script[i]
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture
def sleeps(monkeypatch):
    s = []
    for m in (eac, eap, e107):
        monkeypatch.setattr(m.time, "sleep", lambda x, s=s: s.append(x))
    return s


def pump(i, **kw):
    d = {"id": i, "name": f"P{i}", "company": "IOCL", "state": "Goa", "city": "Panaji", "latitude": "15.5",
         "longitude": "73.8", "petrol_price": "100.5", "has_petrol": True, "has_diesel": True, "has_cng": False}
    d.update(kw)
    return d


# ------------------------------------------------------------------ extract_all_ssri_complete
@pytest.fixture
def ex(monkeypatch):
    return eac.CompleteSSRIExtractor()


def test_add_pumps_dedups_on_id_and_coerces_fields(ex):
    added = ex._add_pumps([pump(1), pump(1), {"name": "no id"}, pump(2, latitude=None, petrol_price=0), pump(3, has_cng=1)])
    assert added == 3 and ex.stats["duplicates"] == 1
    r = ex.all_pumps[1]
    assert r["latitude"] == 15.5 and r["petrol_price"] == 100.5 and r["source"] == "SSRI API"
    assert ex.all_pumps[2]["latitude"] is None and ex.all_pumps[2]["petrol_price"] is None   # falsy -> None
    assert ex.all_pumps[3]["has_cng"] is True


def test_add_pumps_counts_unparseable_records_as_errors(ex):
    assert ex._add_pumps([pump(1, latitude="north")]) == 0
    assert ex.stats["errors"] == 1 and ex.all_pumps == {}


def test_fetch_all_pages_follows_next_until_done(ex, monkeypatch, sleeps):
    net = Net([Resp(200, {"results": [pump(1)], "next": "url"}), Resp(200, {"results": [pump(2)], "next": None})])
    monkeypatch.setattr(eac.requests, "get", net)
    ex.fetch_all_pages()
    assert len(net.calls) == 2 and net.calls[0][1] == {"limit": 100, "page": 1} and net.calls[1][1]["page"] == 2
    assert ex.stats["records_fetched"] == 2 and ex.stats["unique_records"] == 2
    assert 0.2 in sleeps


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="when the last page is reached (`next` is empty) fetch_all_pages() breaks before "
                          "`page += 1`, so stats['total_pages'] = page - 1 under-reports by one")
def test_fetch_all_pages_total_pages_counts_the_last_page(ex, monkeypatch, sleeps):
    monkeypatch.setattr(eac.requests, "get", Net([Resp(200, {"results": [pump(1)], "next": "n"}),
                                                  Resp(200, {"results": [pump(2)], "next": None})]))
    ex.fetch_all_pages()
    assert ex.stats["total_pages"] == 2


def test_fetch_all_pages_stops_after_five_consecutive_failures(ex, monkeypatch, sleeps):
    for script in ([Resp(500)], [Resp(200, {"results": []})], [RuntimeError("boom")]):
        e = eac.CompleteSSRIExtractor()
        net = Net(script)
        monkeypatch.setattr(eac.requests, "get", net)
        e.fetch_all_pages()
        assert len(net.calls) == 5 and e.stats["total_pages"] == 5


def test_fetch_all_pages_failure_counter_resets_on_success(ex, monkeypatch, sleeps):
    ok = Resp(200, {"results": [pump(1)], "next": "n"})
    script = [Resp(500)] * 4 + [ok] + [Resp(500)] * 4 + [Resp(200, {"results": [pump(2)], "next": None})]
    net = Net(script)
    monkeypatch.setattr(eac.requests, "get", net)
    ex.fetch_all_pages()
    assert len(net.calls) == 10 and len(ex.all_pumps) == 2                  # 4 fails + ok + 4 fails + ok: never reaches 5 in a row


def test_fetch_all_pages_respects_max_pages(ex, monkeypatch, sleeps):
    net = Net([Resp(200, {"results": [pump(1)], "next": "n"})])
    monkeypatch.setattr(eac.requests, "get", net)
    ex.fetch_all_pages(max_pages=3)
    assert len(net.calls) == 3 and ex.stats["total_pages"] == 3


def test_export_complete_database(ex, tmp_path):
    assert ex.export_complete_database(str(tmp_path / "none")) is None
    ex._add_pumps([pump(1, has_cng=True), pump(2, company="BPCL", state="Kerala", latitude=None, has_diesel=False)])
    out = tmp_path / "o"
    s = ex.export_complete_database(str(out))
    assert s["total_unique_pumps"] == 2 and s["unique_states"] == 2 and s["unique_companies"] == 2
    assert s["pumps_with_cng"] == 1 and s["pumps_with_prices"] == 2
    assert s["fuel_availability"] == {"has_petrol": 2, "has_diesel": 1, "has_cng": 1, "all_three": 1}
    assert s["company_distribution"] == {"IOCL": 1, "BPCL": 1}
    gj = json.loads(next(out.glob("*.geojson")).read_text())
    assert len(gj["features"]) == 1 and gj["features"][0]["geometry"]["coordinates"] == [73.8, 15.5]
    js = next(out.glob("*.js")).read_text()
    assert "const COMPLETE_FUEL_PUMP_DATABASE = [" in js and '"total": 2' in js
    assert len(json.loads(next(out.glob("ssri_complete_pumps_*.json")).read_text())) == 2
    assert json.loads(next(out.glob("*summary*.json")).read_text())["total_unique_pumps"] == 2
    ex.print_summary(s)


def test_run_and_main(ex, monkeypatch, tmp_path, sleeps):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(eac.requests, "get", Net([Resp(200, {"results": [pump(1)], "next": None})]))
    eac.main()
    assert list((tmp_path / "outlet_data_ssri_107k").glob("ssri_complete_pumps_*.csv"))
    monkeypatch.setattr(eac.requests, "get", Net([Resp(404)]))
    eac.CompleteSSRIExtractor().run()                                         # nothing fetched -> no summary printed


# ------------------------------------------------------------------ extract_all_ssri_pumps
@pytest.fixture
def mp():
    return eap.CompleteSSRIExtractor()


def test_gps_dedup_six_decimal_precision(mp):
    a = {"name": "A", "latitude": 28.7041, "longitude": 77.1025}
    assert mp._add_pumps([a, dict(a), {"name": "B", "lat": "28.7041", "lng": "77.1025"}], "x") == 1     # alt keys, same GPS id
    assert mp.stats["duplicates_found"] == 2
    assert mp._add_pumps([{"name": "C", "latitude": 28.7041004, "longitude": 77.1025}], "x") == 0        # rounds to the same 6dp
    assert mp._add_pumps([{"name": "C", "latitude": 28.704101, "longitude": 77.1025}], "x") == 1         # 1e-6 deg apart: distinct
    assert "28.704100_77.102500" in mp.all_pumps


def test_add_pumps_skips_missing_or_bad_coordinates(mp):
    assert mp._add_pumps([{"name": "n"}, {"name": "z", "latitude": 0, "longitude": 5},
                          {"name": "bad", "latitude": "x", "longitude": 1}], "pagination") == 0
    r = mp._add_pumps([{"name": "ok", "latitude": 1.5, "longitude": 2.5, "phone": 123}], "pagination")
    assert r == 1 and mp.all_pumps["1.500000_2.500000"]["phone"] == "123"
    assert mp.all_pumps["1.500000_2.500000"]["city"] == "Unknown"


def test_extract_all_pages_stops_after_five_empty_and_handles_shapes(mp, monkeypatch, sleeps):
    gp = lambda i: {"name": f"p{i}", "latitude": 10 + i, "longitude": 20}      # noqa: E731
    net = Net([Resp(200, [gp(1)]), Resp(200, {"results": [gp(2)]}), Resp(200, {"data": [gp(3)]})] + [Resp(200, {})])
    monkeypatch.setattr(eap.requests, "get", net)
    mp.extract_all_pages()
    assert len(net.calls) == 3 + 5 and mp.stats["pagination"] == 3            # three shapes accepted; 5 empty pages end it
    assert net.calls[0][1] == {"limit": 1000, "page": 1}


def test_extract_all_pages_non_200_and_exceptions_count_as_empty(mp, monkeypatch, sleeps):
    monkeypatch.setattr(eap.requests, "get", Net([Resp(500)]))
    mp.extract_all_pages()
    assert mp.stats["pagination"] == 0
    mp2 = eap.CompleteSSRIExtractor()
    net = Net([RuntimeError("x")])
    monkeypatch.setattr(eap.requests, "get", net)
    mp2.extract_all_pages(max_pages=4)
    assert len(net.calls) == 4                                                # exceptions advance the page but never count as empty


def test_company_city_and_nearby_strategies(mp, monkeypatch, sleeps):
    def script(url, params):
        if url.endswith("/by-company/"):
            return Resp(200, [{"name": params["company"], "latitude": 10 + ord(params["company"][0]) / 100, "longitude": 1}]) \
                if params["company"] in ("IOCL", "BPCL") else Resp(200, [])
        if url.endswith("/by-city/"):
            return Resp(500) if params["city"] == "Delhi" else Resp(200, {"results": [{"name": params["city"], "latitude": 30 + ord(params["city"][0]) / 100, "longitude": 2}]}) \
                if params["city"] in ("Mumbai", "Pune") else Resp(200, [])
        raise RuntimeError("nearby down")
    monkeypatch.setattr(eap.requests, "get", Net(script))
    mp.extract_by_all_companies()
    assert mp.stats["companies"] == 2
    mp.extract_major_cities()
    assert mp.stats["cities"] == 2
    mp.extract_nearby_searches()                                               # every request raises -> swallowed
    assert mp.stats["nearby"] == 0


def test_nearby_grid_is_17_cities_by_3_radii(mp, monkeypatch, sleeps):
    net = Net([Resp(200, {"results": [{"name": "n", "latitude": 5.5, "longitude": 6.5}]})])
    monkeypatch.setattr(eap.requests, "get", net)
    mp.extract_nearby_searches()
    assert len(net.calls) == 18 * 3                                            # 18 listed locations x 3 radii
    assert sorted({c[1]["radius"] for c in net.calls}) == [10, 25, 50]
    assert mp.stats["nearby"] == 1 and mp.stats["duplicates_found"] == 53


def test_export_all_and_run(mp, monkeypatch, tmp_path, sleeps):
    assert mp.export_all(str(tmp_path / "none")) is None
    mp._add_pumps([{"name": "A", "latitude": 1.5, "longitude": 2.5, "state": "Goa", "company": "IOCL"},
                   {"name": "B", "latitude": 3.5, "longitude": 4.5, "state": "Goa", "company": "BPCL"}], "x")
    out, summary = mp.export_all(str(tmp_path / "o"))
    assert summary["total_pumps"] == 2 and summary["states"] == {"Goa": 2} and summary["unique_companies"] == 2
    assert len(list((tmp_path / "o").glob("ssri_all_pumps_*"))) >= 5
    monkeypatch.setattr(mp, "_export_summary", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
    assert mp.export_all(str(tmp_path / "o2")) == (None, None)


def test_run_complete_extraction_and_main(monkeypatch, tmp_path, sleeps):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(eap.requests, "get", Net([Resp(200, [{"name": "A", "latitude": 1.5, "longitude": 2.5, "state": "Goa", "company": "IOCL"}])]))
    eap.main()
    assert list((tmp_path / "outlet_data_ssri_complete").glob("ssri_all_pumps_*.csv"))


# ------------------------------------------------------------------ extract_ssri_complete_107k
@pytest.fixture
def x107():
    return e107.CompleteSSRIExtractor107K()


def test_fetch_page_success_rate_limit_and_server_errors(x107, monkeypatch, sleeps):
    monkeypatch.setattr(e107.requests, "get", Net([Resp(200, {"results": [pump(1)], "next": "n"})]))
    assert x107.fetch_page_optimized(7) == ([pump(1)], "n", True)
    monkeypatch.setattr(e107.requests, "get", Net([Resp(200, {"results": []})]))
    assert x107.fetch_page_optimized(1) == ([], False, True)
    sleeps.clear()
    monkeypatch.setattr(e107.requests, "get", Net([Resp(429), Resp(429), Resp(200, {"results": [pump(2)]})]))
    res, nxt, ok = x107.fetch_page_optimized(1)
    assert ok and not nxt and sleeps == [5, 10] and x107.stats["rate_limited"] == 2          # back-off 5 s * attempt
    sleeps.clear()
    monkeypatch.setattr(e107.requests, "get", Net([Resp(503), Resp(502), Resp(504)]))
    assert x107.fetch_page_optimized(1) == ([], False, False) and sleeps == [2, 4, 6]
    monkeypatch.setattr(e107.requests, "get", Net([Resp(404)]))
    assert x107.fetch_page_optimized(1) == ([], False, False)


def test_fetch_page_timeout_and_unexpected_errors(x107, monkeypatch, sleeps):
    monkeypatch.setattr(e107.requests, "get", Net([requests.Timeout(), Resp(200, {"results": [pump(1)]})]))
    assert x107.fetch_page_optimized(1)[2] is True and sleeps == [2]
    monkeypatch.setattr(e107.requests, "get", Net([ValueError("x")]))
    assert x107.fetch_page_optimized(1) == ([], False, False)                # non-timeout error: no retry
    net = Net([requests.Timeout()])
    monkeypatch.setattr(e107.requests, "get", net)
    assert x107.fetch_page_optimized(1, retries=2) == ([], False, False) and len(net.calls) == 2


def test_add_pumps_batch_needs_ids(x107):
    assert x107.add_pumps_batch([pump(1), pump(1), {"name": "x"}, pump(0), pump(2, latitude=None)]) == 2
    assert x107.all_pumps[2]["latitude"] is None and x107.all_pumps[1]["phone"] == ""


def test_extract_all_stops_on_no_next_and_after_three_failures(x107, monkeypatch, sleeps):
    net = Net([Resp(200, {"results": [pump(1)], "next": "n"}), Resp(200, {"results": [pump(2)], "next": None}),
               Resp(200, {"results": [pump(3)]})])
    monkeypatch.setattr(e107.requests, "get", net)
    x107.extract_all()
    assert len(net.calls) == 2 and x107.stats["records_fetched"] == 2
    f = e107.CompleteSSRIExtractor107K()
    net = Net([Resp(404)])
    monkeypatch.setattr(e107.requests, "get", net)
    f.extract_all()
    assert len(net.calls) == 3 and f.stats["total_pages"] == 3 and sleeps.count(5) == 3


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="extract_all() breaks on the last page before `page += 1`, so total_pages = page - 1 "
                          "under-reports by one (2 pages fetched, 1 reported)")
def test_extract_all_total_pages_counts_the_last_page(x107, monkeypatch, sleeps):
    monkeypatch.setattr(e107.requests, "get", Net([Resp(200, {"results": [pump(1)], "next": "n"}),
                                                   Resp(200, {"results": [pump(2)], "next": None})]))
    x107.extract_all()
    assert x107.stats["total_pages"] == 2


def test_extract_all_empty_page_ends_and_every_hundredth_sleeps_longer(x107, monkeypatch, sleeps):
    pages = {"n": 0}

    def script(url, params):
        pages["n"] += 1
        return Resp(200, {"results": [pump(pages["n"])], "next": "n"}) if pages["n"] <= 100 else Resp(200, {"results": [], "next": "n"})
    monkeypatch.setattr(e107.requests, "get", Net(script))
    x107.extract_all()
    assert x107.stats["records_fetched"] == 100 and 2 in sleeps and sleeps.count(0.3) == 99


def test_export_data_and_run(x107, monkeypatch, tmp_path, sleeps):
    assert x107.export_data(str(tmp_path / "none")) is None
    x107.add_pumps_batch([pump(1, has_cng=True), pump(2, state="Kerala", company="BPCL", latitude=None, petrol_price=None)])
    out = tmp_path / "o"
    json_path = x107.export_data(str(out))
    assert json_path.endswith(".json") and len(json.loads(open(json_path).read())) == 2
    s = json.loads(next(out.glob("*summary*.json")).read_text())
    assert s == {"timestamp": x107.timestamp, "total_pumps": 2, "states": 2, "companies": 2,
                 "with_coordinates": 1, "with_cng": 1, "with_prices": 1}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(e107.requests, "get", Net([Resp(200, {"results": [pump(9)], "next": None})]))
    e107.main()
    assert list((tmp_path / "outlet_data_ssri_107k").glob("ssri_complete_107k_*.csv"))
