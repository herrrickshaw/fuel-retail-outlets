"""integrate_multi_source_database.py: GPS de-duplication when merging BPCL dealers into SSRI pumps."""
import pytest

from integrate_multi_source_database import MultiSourceDatabaseIntegrator

DEG_PER_KM = 1 / 111.195


def test_haversine_and_bad_input():
    m = MultiSourceDatabaseIntegrator()
    assert m.haversine_distance(0, 0, 1, 0) == pytest.approx(111.195, abs=0.001)
    assert m.haversine_distance("x", 0, 1, 0) == float("inf")


def integrate(ssri, bpcl):
    m = MultiSourceDatabaseIntegrator()
    m.ssri_data, m.bpcl_data = ssri, bpcl
    m.integrate_databases()
    return m


def test_same_company_within_500m_is_merged_and_enriched():
    m = integrate([{"name": "BP Pump", "company": "BPCL", "latitude": 20.0, "longitude": 80.0}],
                  [{"name": "Dealer", "company": "BPCL", "latitude": 20.0 + 0.1 * DEG_PER_KM, "longitude": 80.0,
                    "customer_code": "C1", "postal_code": "400001"}])
    assert len(m.unified_database) == 1
    assert m.unified_database[0]["customer_code"] == "C1"
    assert m.dedup_stats["duplicates_found"] == 1


def test_bpcl_dealer_next_to_an_iocl_pump_is_not_merged_into_it():
    """Two brands 300 m apart are two outlets; the BPCL codes must not land on the IOCL record."""
    m = integrate([{"name": "IO Pump", "company": "IOCL", "latitude": 20.0, "longitude": 80.0}],
                  [{"name": "Dealer", "company": "BPCL", "latitude": 20.0 + 0.3 * DEG_PER_KM, "longitude": 80.0,
                    "customer_code": "C1"}])
    assert len(m.unified_database) == 2
    assert m.unified_database[0]["customer_code"] == ""


def test_far_or_coordinate_less_dealers_are_added():
    m = integrate([{"name": "BP Pump", "company": "BPCL", "latitude": 20.0, "longitude": 80.0}],
                  [{"company": "BPCL", "latitude": 20.0 + 0.6 * DEG_PER_KM, "longitude": 80.0},
                   {"company": "BPCL"}])
    assert len(m.unified_database) == 3
    assert m.dedup_stats["unique_records"] == 3
