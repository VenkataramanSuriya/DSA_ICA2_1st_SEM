"""
tests/test_graph.py — Unit tests for the graph.py algorithmic layer.

Covers:
  1. Baseline shortest path ending at a shelter
  2. Blocking the first edge of optimal path forces reroute
  3. 3× hazard raises cost or changes route
  4. Fully isolated start node → no path / no crash
  5. Start node is itself a shelter → cost 0
  6. Unblocking restores original route
  7. Dijkstra vs Bellman-Ford correctness check
"""

from __future__ import annotations

import math
import sys
import os
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Make sure we can import graph.py from the parent directory ──────────────
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

from graph import Edge, Graph, NodeInfo, RouteResult, load_graph_from_json


# ─────────────────────────────────────────────────────────────────────────────
# BELLMAN-FORD REFERENCE IMPLEMENTATION
# ─────────────────────────────────────────────────────────────────────────────

def bellman_ford(
    graph: Graph,
    start: str,
    targets: Optional[set] = None,
) -> Tuple[Optional[str], float]:
    """
    Bellman-Ford shortest-path for verification purposes.

    Time: O(V × E) — much slower than Dijkstra, but guaranteed correct.
    We use this as a reference oracle to verify Dijkstra results.

    Returns (best_shelter_id, cost) or (None, inf) if unreachable.
    """
    if targets is None:
        targets = graph.get_shelters()

    nodes = list(graph.get_all_nodes().keys())
    dist: Dict[str, float] = {n: math.inf for n in nodes}
    dist[start] = 0.0

    # Collect all directed edges for Bellman-Ford iteration
    all_edges: List[Tuple[str, str, float]] = []
    for eid, (fwd, _) in graph.get_all_edge_pairs().items():
        w = fwd.effective_weight()
        if not math.isinf(w):
            all_edges.append((fwd.from_node, fwd.to_node, w))
            bwd_pair = graph.get_edge_pair(eid)
            if bwd_pair:
                bw = bwd_pair[1].effective_weight()
                if not math.isinf(bw):
                    all_edges.append((bwd_pair[1].from_node, bwd_pair[1].to_node, bw))

    # Relax all edges |V| - 1 times
    for _ in range(len(nodes) - 1):
        updated = False
        for u, v, w in all_edges:
            if dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
                updated = True
        if not updated:
            break

    # Find best shelter
    best: Optional[str] = None
    best_cost = math.inf
    for t in targets:
        if dist[t] < best_cost:
            best_cost = dist[t]
            best = t

    return best, best_cost


# ─────────────────────────────────────────────────────────────────────────────
# TEST HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def build_sample_graph() -> Graph:
    """
    Build a small deterministic graph for testing:

        A ─4─ B ─5─ C
        |           |
        4           3
        |           |
        E ─4─ F ─4─ G

    Shelters: C, G.  Start: A.
    Optimal path A→B→C (cost 9) or A→E→F→G (cost 12).
    So shelter C is closer.
    """
    g = Graph()
    g.city_name = "TestCity"
    for nid, lbl, x, y, ntype in [
        ("A", "Alpha",   0,  0, "normal"),
        ("B", "Beta",   100, 0, "normal"),
        ("C", "Shelter-C", 200, 0, "shelter"),
        ("E", "Echo",    0, 100, "normal"),
        ("F", "Fox",    100, 100, "normal"),
        ("G", "Shelter-G", 200, 100, "shelter"),
    ]:
        g.add_node(NodeInfo(nid, lbl, x, y, ntype))

    g.add_bidirectional_edge("e1", "A", "B", 4.0)
    g.add_bidirectional_edge("e2", "B", "C", 5.0)
    g.add_bidirectional_edge("e3", "A", "E", 4.0)
    g.add_bidirectional_edge("e4", "E", "F", 4.0)
    g.add_bidirectional_edge("e5", "F", "G", 4.0)
    g.add_bidirectional_edge("e6", "B", "F", 3.0)   # diagonal shortcut
    return g


# ─────────────────────────────────────────────────────────────────────────────
# TEST CASES
# ─────────────────────────────────────────────────────────────────────────────

class TestBaseline(unittest.TestCase):
    """Test 1: Baseline shortest path returns a valid path ending at a shelter."""

    def test_baseline_path_ends_at_shelter(self) -> None:
        g = build_sample_graph()
        result = g.dijkstra("A")
        self.assertTrue(result.reachable, "Should find a reachable route")
        self.assertIn(result.destination, g.get_shelters(),
                      "Destination must be a shelter")
        self.assertGreater(len(result.path), 0, "Path must be non-empty")
        self.assertEqual(result.path[0], "A", "Path must start at A")
        self.assertEqual(result.path[-1], result.destination,
                         "Last path node must equal destination shelter")

    def test_baseline_cost_is_positive(self) -> None:
        g = build_sample_graph()
        result = g.dijkstra("A")
        self.assertGreater(result.total_cost, 0.0)
        self.assertFalse(math.isinf(result.total_cost))

    def test_baseline_chooses_cheaper_shelter(self) -> None:
        """A→B→C costs 9 (via diagonal shortcut A→B costs 4, B→C costs 5)."""
        g = build_sample_graph()
        result = g.dijkstra("A")
        self.assertEqual(result.destination, "C",
                         f"Should prefer C (cost 9) over G; got {result.destination}")
        self.assertAlmostEqual(result.total_cost, 9.0, places=1)


class TestBlockFirstEdge(unittest.TestCase):
    """Test 2: Blocking the first edge of optimal path forces a different route."""

    def test_block_forces_reroute(self) -> None:
        g = build_sample_graph()
        # Baseline: A→B→C (cost 9). Block e1 (A-B).
        g.toggle_edge_blocked("e1")
        result = g.dijkstra("A")
        self.assertTrue(result.reachable, "Should still find a route after blocking e1")
        # A→B is now blocked; path must not use it as first edge
        if len(result.path) >= 2:
            self.assertFalse(
                result.path[0] == "A" and result.path[1] == "B",
                f"Path should not go A→B when e1 is blocked. Got: {result.path}",
            )

    def test_block_e1_uses_longer_route(self) -> None:
        """With A-B blocked, cheapest path is A→E→F→B→C (via shortcut e6) = 4+4+3+5=16
           or A→E→F→G = 4+4+4 = 12. So should go to G (cost 12)."""
        g = build_sample_graph()
        g.toggle_edge_blocked("e1")
        result = g.dijkstra("A")
        self.assertEqual(result.destination, "G",
                         f"Should reroute to G after blocking A-B; got {result.destination}")
        self.assertAlmostEqual(result.total_cost, 12.0, places=1)


class TestHazardModifier(unittest.TestCase):
    """Test 3: A 3× hazard on a path edge raises cost or changes the route."""

    def test_hazard_raises_cost(self) -> None:
        g = build_sample_graph()
        baseline = g.dijkstra("A")
        # Apply 3× hazard to both edges on A→B→C route
        g.cycle_edge_hazard("e1")   # 1x → 2x
        g.cycle_edge_hazard("e1")   # 2x → 3x
        g.cycle_edge_hazard("e2")
        g.cycle_edge_hazard("e2")
        result = g.dijkstra("A")
        # Either cost is higher, or a different (cheaper effective) shelter chosen
        self.assertTrue(
            result.total_cost > baseline.total_cost or result.destination != baseline.destination,
            "Hazard must raise cost or force reroute",
        )

    def test_hazard_3x_on_short_path_switches_shelter(self) -> None:
        """3× on e1+e2 → A→B (12) + B→C (15) = 27 to C.
           But A→E→F→G costs 12. So router should switch to G."""
        g = build_sample_graph()
        for _ in range(2):
            g.cycle_edge_hazard("e1")
            g.cycle_edge_hazard("e2")
        result = g.dijkstra("A")
        self.assertEqual(result.destination, "G",
                         f"Should switch to G after 3× hazard on A→B→C path; got {result.destination}")


class TestIsolatedStart(unittest.TestCase):
    """Test 4: Fully isolating the start node returns no path, with no crash."""

    def test_isolated_start_returns_no_route(self) -> None:
        g = build_sample_graph()
        # Block all edges from A (e1=A-B, e3=A-E)
        g.toggle_edge_blocked("e1")
        g.toggle_edge_blocked("e3")
        result = g.dijkstra("A")
        self.assertFalse(result.reachable, "Isolated start should report not reachable")
        self.assertIsNone(result.destination)
        self.assertTrue(math.isinf(result.total_cost))
        self.assertEqual(result.path, [])

    def test_no_crash_on_isolated_node(self) -> None:
        """Ensure Dijkstra does not crash on isolated node."""
        g = build_sample_graph()
        g.toggle_edge_blocked("e1")
        g.toggle_edge_blocked("e3")
        try:
            _ = g.dijkstra("A")
        except Exception as exc:
            self.fail(f"Dijkstra raised exception on isolated node: {exc}")


class TestStartIsShelter(unittest.TestCase):
    """Test 5: Start node that is itself a shelter returns cost 0."""

    def test_shelter_start_cost_zero(self) -> None:
        g = build_sample_graph()
        result = g.dijkstra("C")   # C is a shelter
        self.assertTrue(result.reachable)
        self.assertAlmostEqual(result.total_cost, 0.0)
        self.assertEqual(result.destination, "C")
        self.assertEqual(result.path, ["C"])
        self.assertEqual(result.nodes_visited, 0,
                         "Already at shelter: no nodes need to be visited")

    def test_other_shelter_start(self) -> None:
        g = build_sample_graph()
        result = g.dijkstra("G")
        self.assertAlmostEqual(result.total_cost, 0.0)
        self.assertEqual(result.destination, "G")


class TestUnblockRestoresRoute(unittest.TestCase):
    """Test 6: Unblocking restores the original route."""

    def test_unblock_restores(self) -> None:
        g = build_sample_graph()
        baseline = g.dijkstra("A")
        g.toggle_edge_blocked("e1")  # Block
        rerouted = g.dijkstra("A")
        g.toggle_edge_blocked("e1")  # Unblock
        restored = g.dijkstra("A")
        self.assertEqual(restored.destination, baseline.destination,
                         "Restored destination should match baseline")
        self.assertAlmostEqual(restored.total_cost, baseline.total_cost, places=1,
                               msg="Restored cost should match baseline")
        self.assertNotEqual(rerouted.destination, restored.destination,
                            "Rerouted destination should differ from restored (otherwise test is vacuous)")


class TestDijkstraVsBellmanFord(unittest.TestCase):
    """Test 7: Dijkstra results match Bellman-Ford on the sample map."""

    def _verify_match(self, g: Graph, start: str) -> None:
        d_result = g.dijkstra(start)
        bf_shelter, bf_cost = bellman_ford(g, start)

        if not d_result.reachable:
            self.assertIsNone(bf_shelter,
                              f"Dijkstra says no route from {start} but BF found {bf_shelter}")
        else:
            self.assertIsNotNone(bf_shelter,
                                 f"Dijkstra found route but BF says none from {start}")
            self.assertAlmostEqual(
                d_result.total_cost, bf_cost, places=3,
                msg=f"Cost mismatch from {start}: Dijkstra={d_result.total_cost}, BF={bf_cost}",
            )

    def test_baseline_match(self) -> None:
        g = build_sample_graph()
        self._verify_match(g, "A")

    def test_with_hazard_match(self) -> None:
        g = build_sample_graph()
        g.cycle_edge_hazard("e1")   # 2×
        self._verify_match(g, "A")

    def test_with_block_match(self) -> None:
        g = build_sample_graph()
        g.toggle_edge_blocked("e1")
        self._verify_match(g, "A")

    def test_all_nodes_match(self) -> None:
        """Run both algorithms from every non-shelter node and compare."""
        g = build_sample_graph()
        for nid in ["A", "B", "E", "F"]:
            with self.subTest(start=nid):
                self._verify_match(g, nid)

    def test_with_rivermead_map(self) -> None:
        """Load the real map_data.json and cross-check Dijkstra vs Bellman-Ford."""
        map_path = _ROOT / "map_data.json"
        if not map_path.exists():
            self.skipTest("map_data.json not found — skipping real-map test")
        g = load_graph_from_json(map_path)
        for start in ["A", "E", "J", "L"]:
            with self.subTest(start=start):
                self._verify_match(g, start)


class TestEdgeCasesAdditional(unittest.TestCase):
    """Additional edge case tests for robustness."""

    def test_effective_weight_blocked(self) -> None:
        """Blocked edge returns math.inf from effective_weight()."""
        e = Edge("x", "A", "B", 5.0, blocked=True)
        self.assertTrue(math.isinf(e.effective_weight()))

    def test_effective_weight_hazard(self) -> None:
        """Hazard multiplier is correctly applied."""
        e = Edge("x", "A", "B", 4.0, hazard_multiplier=2.0)
        self.assertAlmostEqual(e.effective_weight(), 8.0)

    def test_effective_weight_normal(self) -> None:
        e = Edge("x", "A", "B", 7.0)
        self.assertAlmostEqual(e.effective_weight(), 7.0)

    def test_cycle_hazard_wraps(self) -> None:
        """Cycling hazard goes 1.0 → 2.0 → 3.0 → 1.0."""
        e = Edge("x", "A", "B", 4.0)
        self.assertAlmostEqual(e.hazard_multiplier, 1.0)
        e.cycle_hazard()
        self.assertAlmostEqual(e.hazard_multiplier, 2.0)
        e.cycle_hazard()
        self.assertAlmostEqual(e.hazard_multiplier, 3.0)
        e.cycle_hazard()
        self.assertAlmostEqual(e.hazard_multiplier, 1.0)

    def test_reset_edge(self) -> None:
        """Edge reset clears blocked and multiplier."""
        e = Edge("x", "A", "B", 5.0, blocked=True, hazard_multiplier=3.0)
        e.reset()
        self.assertFalse(e.blocked)
        self.assertAlmostEqual(e.hazard_multiplier, 1.0)

    def test_nodes_visited_metric(self) -> None:
        """Nodes visited should be ≥ 1 and ≤ total nodes when route found."""
        g = build_sample_graph()
        result = g.dijkstra("A")
        if result.reachable:
            self.assertGreaterEqual(result.nodes_visited, 1)
            self.assertLessEqual(result.nodes_visited, g.node_count)

    def test_exec_time_positive(self) -> None:
        g = build_sample_graph()
        result = g.dijkstra("A")
        self.assertGreaterEqual(result.exec_time_ms, 0.0)

    def test_path_continuity(self) -> None:
        """Every consecutive pair in the path must share an edge."""
        g = build_sample_graph()
        result = g.dijkstra("A")
        if not result.reachable:
            return
        for i in range(len(result.path) - 1):
            u, v = result.path[i], result.path[i + 1]
            neighbors = [e.to_node for e in g.neighbors(u)]
            self.assertIn(v, neighbors,
                          f"No direct edge from {u} to {v} in path {result.path}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
