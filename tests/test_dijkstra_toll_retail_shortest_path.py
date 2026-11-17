"""dijkstra_toll_retail_shortest_path.py: graph maths and toll placement."""
import math

import pandas as pd
import pytest

import dijkstra_toll_retail_shortest_path as m

KM_PER_DEG = 6371 * math.pi / 180  # 111.195 km per degree of latitude


def test_haversine_one_degree_latitude():
    g = m.DijkstraGraph()
    assert g.haversine_distance(0, 0, 1, 0) == pytest.approx(KM_PER_DEG, rel=1e-9)
    assert g.haversine_distance(10, 20, 10, 20) == 0


def graph(edges, extra=()):
    g = m.DijkstraGraph()
    for v in {x for e in edges for x in e[:2]} | set(extra):
        g.add_vertex(v, "petrol_pump" if v.startswith("O") else "toll_plaza", 0, 0)
    for u, v, w in edges:
        g.add_edge(u, v, w)
    return g


def test_dijkstra_hand_graph_and_path():
    g = graph([("S", "A", 1), ("S", "B", 4), ("A", "B", 2), ("B", "C", 1)], extra=["Z"])
    sp = m.DijkstraShortestPath(g)
    dist, pred = sp.dijkstra("S")
    assert dist == {"S": 0, "A": 1, "B": 3, "C": 4, "Z": float("inf")}
    sp.results["S"] = {"distances": dist, "predecessors": pred}
    assert sp.reconstruct_path("S", "C") == ["S", "A", "B", "C"]
    assert sp.reconstruct_path("S", "Z") == []


def test_zero_length_edge_is_kept():
    """An outlet at the plaza's own coordinates is 0 km away, not unreachable."""
    g = graph([("T", "O1", 0.0)])
    dist, _ = m.DijkstraShortestPath(g).dijkstra("T")
    assert dist["O1"] == 0.0


def test_min_distance_is_nearest_outlet_not_the_source_itself(capsys):
    g = graph([("T1", "O1", 5.0), ("T1", "O2", 3.0), ("T1", "T2", 1.0)])
    sp = m.DijkstraShortestPath(g)
    sp.find_shortest_paths_from_tolls(["T1"])
    r = sp.results["T1"]
    assert r["min_distance"] == 3.0
    assert r["visited"] == 2  # outlets reachable, not counting the source or other tolls


def test_build_graph_uses_plaza_coordinates_and_never_collapses_a_state(toll_csv, ssri_json):
    toll_csv(pd.DataFrame({
        "plaza_name": ["Vasad Toll Plaza", "Bamanbore Toll Plaza", "No Coords Toll Plaza"],
        "state": ["Gujarat", "Gujarat", "Gujarat"],
        "latitude": [22.45, 22.41, None], "longitude": [73.07, 71.07, None],
    }))
    ssri_json(m, [{"id": 1, "latitude": "22.46", "longitude": "73.08"}])
    a = m.TollRetailShortestPathAnalyzer()
    a.build_graph()
    coords = [(t["lat"], t["lng"]) for t in a.toll_plazas]
    assert coords == [(22.45, 73.07), (22.41, 71.07)]  # real points; no fabricated location for the 3rd


def test_build_graph_does_not_invent_coordinates_from_state(toll_csv, ssri_json):
    toll_csv(pd.DataFrame({"plaza_name": ["A Toll Plaza", "B Toll Plaza", "C Toll Plaza"],
                           "state": ["Gujarat", "Gujarat", "Nowhere"]}))
    ssri_json(m, [])
    a = m.TollRetailShortestPathAnalyzer()
    a.build_graph()
    assert a.toll_plazas == []
