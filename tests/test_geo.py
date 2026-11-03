"""Characterisation tests: geo.py reproduces the distances of the original per-script copies."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api-data-integration"))

from geo import haversine_km, haversine_km_nonzero_or_inf, haversine_km_or_inf  # noqa: E402

# Values captured from the pre-refactor DijkstraGraph.haversine_distance (main @ 2026-11-02).
CASES = [
    ((28.6139, 77.2090, 19.0760, 72.8777), 1148.0948730375999),
    ((12.9716, 77.5946, 13.0827, 80.2707), 290.1720249530612),
    ((0, 0, 0, 0), 0.0),
    ((10.5, 76.2, 10.5001, 76.2001), 0.015594230792726387),
]


def test_matches_original_values():
    for args, expected in CASES:
        assert haversine_km(*args) == expected


def test_or_inf_variant():
    assert haversine_km_or_inf(None, 1, 2, 3) == math.inf
    assert haversine_km_or_inf("x", 1, 2, 3) == math.inf
    assert haversine_km_or_inf(*CASES[0][0]) == CASES[0][1]


def test_nonzero_guard_variant():
    assert haversine_km_nonzero_or_inf(0, 0, 0, 0) == math.inf
    assert haversine_km_nonzero_or_inf(None, 1, 2, 3) == math.inf
    assert haversine_km_nonzero_or_inf(*CASES[1][0]) == CASES[1][1]


def test_script_wrappers_delegate():
    import create_toll_retail_distance_map as m1
    import dijkstra_filtered_service_outlets as m2
    import dijkstra_toll_retail_shortest_path as m3
    import integrate_toll_retail_database as m4

    a = CASES[0][0]
    assert m3.DijkstraGraph().haversine_distance(*a) == CASES[0][1]
    assert m1.TollRetailDistanceAnalyzer.haversine_distance(None, *a) == CASES[0][1]
    assert m4.TollRetailIntegrator.haversine_distance(None, *a) == CASES[0][1]
    assert m4.TollRetailIntegrator.haversine_distance(None, 0, 1, 2, 3) == math.inf
    assert hasattr(m2, "ServiceFilteredDijkstra")
