"""create_toll_retail_distance_map.py: nearest-outlet table and radius counts."""
import pandas as pd
import pytest

import create_toll_retail_distance_map as m

DEG_PER_KM = 1 / 111.195


def analyzer_with(outlet_offsets_km, toll=(20.0, 80.0)):
    a = m.TollRetailDistanceAnalyzer()
    a.toll_plazas = [{"id": 0, "name": "T", "highway": "NH-1", "state": "S", "lat": toll[0], "lng": toll[1]}]
    a.retail_outlets = [{"id": i, "name": f"O{i}", "company": "X", "city": "c", "has_cng": False,
                         "lat": toll[0] + km * DEG_PER_KM, "lng": toll[1]} for i, km in enumerate(outlet_offsets_km)]
    a.calculate_distances()
    return a


def test_closest_ten_sorted_and_min_distance():
    a = analyzer_with([30, 2, 7, 0.5, 12, 3, 4, 40, 9, 8, 6, 60])
    row = a.distance_matrix[0]
    d = [o["distance"] for o in row["closest_outlets"]]
    assert len(d) == 10 and d == sorted(d)
    assert row["min_distance"] == pytest.approx(0.5, abs=0.01)
    assert 60 not in [round(x) for x in d] and 40 not in [round(x) for x in d]


def test_per_toll_radius_counts_are_not_capped_at_ten():
    a = analyzer_with([0.2 + 0.02 * i for i in range(15)])
    row = a.distance_matrix[0]
    assert row["outlets_1km"] == 15
    assert a.stats["outlets_within_1km"] == 15


def test_load_toll_plazas_uses_plaza_coordinates(toll_csv):
    toll_csv(pd.DataFrame({"plaza_name": ["P1 Toll Plaza", "P2 Toll Plaza", "P3 Toll Plaza"],
                           "state": ["Gujarat", "Gujarat", "Gujarat"], "highway": ["NH-48"] * 3,
                           "latitude": [22.45, 22.41, None], "longitude": [73.07, 71.07, None]}))
    a = m.TollRetailDistanceAnalyzer()
    assert a.load_toll_plazas()
    assert [(t["lat"], t["lng"]) for t in a.toll_plazas] == [(22.45, 73.07), (22.41, 71.07)]
