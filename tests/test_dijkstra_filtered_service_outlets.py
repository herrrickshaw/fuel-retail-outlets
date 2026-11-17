"""dijkstra_filtered_service_outlets.py: toll placement and the per-toll search loop."""
import pandas as pd

import dijkstra_filtered_service_outlets as m


def test_load_toll_plazas_uses_coordinates_and_skips_missing(toll_csv):
    toll_csv(pd.DataFrame({"plaza_name": ["P1", "P2", "P3"], "state": ["Haryana"] * 3,
                           "latitude": [28.40, 29.10, None], "longitude": [76.99, 77.00, None]}))
    a = m.ServiceFilteredDijkstra()
    a.load_toll_plazas()
    assert [(t["lat"], t["lng"]) for t in a.toll_plazas] == [(28.40, 76.99), (29.10, 77.00)]


def test_nearest_service_outlet_and_toll_without_reachable_outlet():
    a = m.ServiceFilteredDijkstra()
    g = a.graph
    for vid, lat in (("T2", 25.0), ("T1", 20.0)):  # T2 (no outlets) first
        g.add_vertex(vid, "toll_plaza", lat, 80.0)
        a.toll_plazas.append({"id": vid, "lat": lat, "lng": 80.0})
    for vid, lat in (("S1", 20.1), ("S2", 20.5)):
        g.add_vertex(vid, "service_outlet", lat, 80.0)
        a.service_outlets.append({"id": vid, "lat": lat, "lng": 80.0})
    g.add_edge("T1", "S1", 11.1)
    g.add_edge("T1", "S2", 55.6)
    # T2 has no edges at all: must not crash or report T1's distance for it
    a.find_shortest_service_paths()
    assert a.results["T1"]["min_service_distance"] == 11.1
    assert a.results["T1"]["service_outlets_reachable"] == 2
    assert "T2" not in a.results
    assert a.stats["avg_distance_to_service"] == 11.1
