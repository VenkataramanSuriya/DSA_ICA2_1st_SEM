"""
graph.py — Pure algorithmic layer: Graph model + Dijkstra's Algorithm.

ZERO UI imports in this file. This keeps the algorithm independent of
the presentation layer (separation of concerns / clean architecture).

DSA Concepts implemented:
  1. Adjacency List Graph Representation  — O(V + E) space
  2. Dijkstra's Algorithm with Binary Min-Heap — O((V + E) log V) time
  3. Dynamic hazard modifiers via effective_weight()
  4. Multi-destination single-pass routing
"""

from __future__ import annotations

import heapq
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NodeInfo:
    """Stores metadata for a single intersection/node in the city graph."""

    node_id: str
    label: str
    x: float
    y: float
    node_type: str = "normal"   # "normal" | "shelter"

    @property
    def is_shelter(self) -> bool:
        """Return True if this node is an emergency shelter."""
        return self.node_type == "shelter"


@dataclass
class Edge:
    """
    Represents one directed half of a bidirectional road segment.

    DSA Concept — Edge with dynamic weight:
      An Edge stores a *base_weight* (the default travel time in minutes)
      and a *hazard_multiplier* that represents environmental danger.
      Blocking a road effectively makes it infinite cost.
      Dijkstra ALWAYS calls effective_weight() so the algorithm
      transparently adapts to live conditions without restarting.

    Space: O(1) per edge object.
    """

    edge_id: str          # Shared ID with the reverse twin edge
    from_node: str        # Source node ID
    to_node: str          # Destination node ID
    base_weight: float    # Travel time under normal conditions (minutes)
    blocked: bool = False                  # True → road is impassable
    hazard_multiplier: float = 1.0         # 1.0 = normal, 2.0 = slow, 3.0 = very slow

    def effective_weight(self) -> float:
        """
        DSA Concept — Dynamic Edge Cost:
          Returns math.inf if the road is blocked (Dijkstra will never
          select an infinite-cost edge, so blocked roads are naturally
          excluded from shortest paths).
          Otherwise returns base_weight × hazard_multiplier.
          Time: O(1).
        """
        if self.blocked:
            return math.inf
        return self.base_weight * self.hazard_multiplier

    def cycle_hazard(self) -> None:
        """
        Cycle hazard multiplier: 1.0 → 2.0 → 3.0 → 1.0.
        If the road is blocked, cycling is still allowed (affects unblock state).
        """
        if self.hazard_multiplier < 1.5:
            self.hazard_multiplier = 2.0
        elif self.hazard_multiplier < 2.5:
            self.hazard_multiplier = 3.0
        else:
            self.hazard_multiplier = 1.0

    def toggle_blocked(self) -> None:
        """Toggle the blocked state of this edge."""
        self.blocked = not self.blocked

    def reset(self) -> None:
        """Restore edge to default (unblocked, no hazard)."""
        self.blocked = False
        self.hazard_multiplier = 1.0


@dataclass
class RouteResult:
    """
    Encapsulates the full result of a Dijkstra routing query.

    Fields:
      path          — Ordered list of node IDs from start to destination.
      destination   — The chosen shelter node ID (None if no route).
      total_cost    — Sum of effective_weight() along the path (minutes).
      nodes_visited — Count of heap pops that finalized a node (algorithm metric).
      exec_time_ms  — Wall-clock execution time measured by perf_counter.
      reachable     — False if no shelter could be reached.
      message       — Human-readable status string.
    """

    path: List[str] = field(default_factory=list)
    destination: Optional[str] = None
    total_cost: float = 0.0
    nodes_visited: int = 0
    exec_time_ms: float = 0.0
    reachable: bool = True
    message: str = "OK"


# ─────────────────────────────────────────────────────────────────────────────
# GRAPH
# ─────────────────────────────────────────────────────────────────────────────

class Graph:
    """
    DSA Concept — Adjacency List Graph Representation:
      We store the graph as a dict mapping each node ID to a list of Edge
      objects that leave from that node.  This is an *adjacency list*.

      Space complexity: O(V + E)
        — V entries in the dict (one per node)
        — E total Edge objects across all lists (one per directed edge;
          a bidirectional road becomes TWO directed Edge objects sharing
          an edge_id, so actually 2E objects for E undirected roads).

      Compare with adjacency *matrix* (V×V array):
        — O(V²) space, fast O(1) edge lookup but wastes memory for
          sparse city graphs (most intersections connect to only 2–4 others).
        — For Rivermead District (12 nodes, 22 undirected roads),
          the matrix would be 144 cells vs our 44 directed Edge objects.

      We choose the adjacency list because city graphs are sparse and
      Dijkstra only iterates over actual neighbors, not all V nodes.
    """

    def __init__(self) -> None:
        """Initialize an empty graph."""
        # Adjacency list: node_id → list of outgoing Edge objects
        self._adj: Dict[str, List[Edge]] = {}
        # Node metadata store
        self._nodes: Dict[str, NodeInfo] = {}
        # Edge registry: edge_id → (forward_Edge, backward_Edge)
        # Allows O(1) access to both halves of a bidirectional road
        self._edge_pairs: Dict[str, Tuple[Edge, Edge]] = {}
        # Shelter set for O(1) lookup
        self._shelters: set[str] = set()
        # City metadata
        self.city_name: str = "Unknown"

    # ── Graph Construction ────────────────────────────────────────────────

    def add_node(self, info: NodeInfo) -> None:
        """Add an intersection node to the graph."""
        self._nodes[info.node_id] = info
        if info.node_id not in self._adj:
            self._adj[info.node_id] = []
        if info.is_shelter:
            self._shelters.add(info.node_id)

    def add_bidirectional_edge(
        self,
        edge_id: str,
        from_id: str,
        to_id: str,
        weight: float,
    ) -> None:
        """
        Add a bidirectional road as two directed Edge objects sharing one edge_id.

        This mirrors how real roads work: you can drive either direction.
        Both halves share the same edge_id so the UI can look up and modify
        both with one key (e.g., toggle_blocked updates both twins).
        """
        fwd = Edge(edge_id=edge_id, from_node=from_id, to_node=to_id, base_weight=weight)
        bwd = Edge(edge_id=edge_id, from_node=to_id,   to_node=from_id, base_weight=weight)
        self._adj[from_id].append(fwd)
        self._adj[to_id].append(bwd)
        self._edge_pairs[edge_id] = (fwd, bwd)

    # ── Edge Manipulation ─────────────────────────────────────────────────

    def toggle_edge_blocked(self, edge_id: str) -> None:
        """Toggle blocked state on both halves of a bidirectional edge."""
        fwd, bwd = self._edge_pairs[edge_id]
        new_state = not fwd.blocked
        fwd.blocked = new_state
        bwd.blocked = new_state

    def cycle_edge_hazard(self, edge_id: str) -> None:
        """Cycle hazard multiplier on both halves of a bidirectional edge."""
        fwd, bwd = self._edge_pairs[edge_id]
        fwd.cycle_hazard()
        bwd.hazard_multiplier = fwd.hazard_multiplier

    def reset_all_edges(self) -> None:
        """Reset every edge to base state (unblocked, multiplier = 1.0)."""
        for fwd, bwd in self._edge_pairs.values():
            fwd.reset()
            bwd.reset()

    def reset_edge(self, edge_id: str) -> None:
        """Reset a single edge pair to base state."""
        fwd, bwd = self._edge_pairs[edge_id]
        fwd.reset()
        bwd.reset()

    # ── Accessors ─────────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> Optional[NodeInfo]:
        """Return NodeInfo for the given node_id, or None if not found."""
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> Dict[str, NodeInfo]:
        """Return a copy of the node registry."""
        return dict(self._nodes)

    def get_edge_pair(self, edge_id: str) -> Optional[Tuple[Edge, Edge]]:
        """Return the (forward, backward) Edge tuple for an edge_id."""
        return self._edge_pairs.get(edge_id)

    def get_all_edge_pairs(self) -> Dict[str, Tuple[Edge, Edge]]:
        """Return a copy of the edge pairs registry."""
        return dict(self._edge_pairs)

    def get_shelters(self) -> set[str]:
        """Return the set of shelter node IDs."""
        return set(self._shelters)

    def neighbors(self, node_id: str) -> List[Edge]:
        """Return all outgoing edges from a node (empty list if unknown node)."""
        return self._adj.get(node_id, [])

    @property
    def node_count(self) -> int:
        """Number of nodes (intersections) in the graph."""
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        """Number of undirected edges (roads) in the graph."""
        return len(self._edge_pairs)

    # ── Dijkstra's Algorithm ──────────────────────────────────────────────

    def dijkstra(
        self,
        start: str,
        targets: Optional[set[str]] = None,
    ) -> RouteResult:
        """
        DSA Concept — Dijkstra's Shortest-Path Algorithm with Binary Min-Heap:

        OVERVIEW:
          Dijkstra finds the minimum-cost path from *start* to all other nodes
          in a graph with non-negative edge weights.  We use a *priority queue*
          (binary min-heap via Python's heapq module) so we always process the
          currently cheapest unfinished node first (greedy choice).

        GREEDY CORRECTNESS ARGUMENT:
          When a node is "finalized" (popped from the heap and not yet seen),
          its recorded distance is provably optimal.  This works because:
          (a) All edge weights are ≥ 0 (guaranteed by effective_weight).
          (b) Once finalized, no shorter path can arrive later — any future
              path through an unfinalized node must be at least as costly.

        TIME COMPLEXITY:  O((V + E) log V)
          — Each of V nodes is inserted into and extracted from the heap once:
            O(V log V) for all pops.
          — Each of E directed edges triggers at most one heap push:
            O(E log V) for all pushes.
          — Total: O((V + E) log V).

          Compare with a naive array scan of distances: O(V²) time.
          For dense graphs, O(V²) ≈ O(E log V), but for sparse city graphs
          where E ≈ 4V, the heap version is dramatically faster.

        SPACE COMPLEXITY:  O(V + E)
          — dist[], prev[] dictionaries: O(V) each.
          — Heap: at most O(E) entries in the worst case.

        STALE ENTRY SKIP:
          Python's heapq does not support efficient key-decrease, so we use
          the standard "lazy deletion" trick: when we push a new (cost, node)
          entry, the old entry for that node remains in the heap.  When it is
          eventually popped, we skip it because the node is already in
          *finalized*.  This does not affect correctness or asymptotic complexity.

        MULTI-DESTINATION SINGLE PASS:
          We pass *targets* (the shelter set) and stop as soon as the cheapest
          shelter is finalized.  One Dijkstra pass is sufficient for all shelters
          because the finalization order is globally cost-sorted.

        EDGE RELAXATION (the inner loop):
          For each neighbor reached via edge e:
            new_cost = dist[current] + e.effective_weight()
            if new_cost < dist[neighbor]:
                dist[neighbor] = new_cost   ← RELAXATION
                prev[neighbor] = current
                heapq.heappush(heap, (new_cost, neighbor))

        Args:
            start:   Source node ID (evacuation origin).
            targets: Optional set of destination node IDs (shelters).
                     If None, uses all shelter nodes in the graph.

        Returns:
            RouteResult with path, cost, and performance metrics.
        """
        t_start = time.perf_counter()

        if targets is None:
            targets = self._shelters

        # ── Edge case: start is already a shelter ─────────────────────────
        if start in targets:
            node = self._nodes.get(start)
            label = node.label if node else start
            return RouteResult(
                path=[start],
                destination=start,
                total_cost=0.0,
                nodes_visited=0,
                exec_time_ms=(time.perf_counter() - t_start) * 1000,
                reachable=True,
                message=f"Already at shelter: {label} (0 min)",
            )

        # ── Initialization ────────────────────────────────────────────────
        # dist[v] = best known cost to reach v from start
        dist: Dict[str, float] = {n: math.inf for n in self._nodes}
        dist[start] = 0.0

        # prev[v] = predecessor node on the shortest path to v
        prev: Dict[str, Optional[str]] = {n: None for n in self._nodes}

        # Binary min-heap entries: (cost, node_id)
        # We store node_id as str; tie-break is lexicographic (acceptable here)
        heap: List[Tuple[float, str]] = [(0.0, start)]

        # finalized: nodes whose shortest distance is confirmed (O(1) lookup)
        finalized: set[str] = set()

        nodes_visited: int = 0    # Count of finalized nodes (algorithm metric)
        best_shelter: Optional[str] = None
        best_cost: float = math.inf

        # ── Main Dijkstra loop ────────────────────────────────────────────
        while heap:
            cost, u = heapq.heappop(heap)   # Always the cheapest unfinished node

            # STALE ENTRY SKIP: if already finalized, this is an old heap entry
            if u in finalized:
                continue

            # FINALIZE this node — its distance is now optimal
            finalized.add(u)
            nodes_visited += 1

            # MULTI-DESTINATION CHECK: stop early if we finalized a shelter
            if u in targets:
                best_shelter = u
                best_cost = cost
                break

            # EDGE RELAXATION: look at every road leaving node u
            for edge in self._adj.get(u, []):
                w = edge.effective_weight()
                if math.isinf(w):
                    continue     # Blocked or infinite-cost roads: skip entirely

                v = edge.to_node
                if v in finalized:
                    continue     # Already optimal; no need to reconsider

                new_cost = cost + w
                if new_cost < dist[v]:
                    # Found a cheaper path to v → RELAX the edge
                    dist[v] = new_cost
                    prev[v] = u
                    heapq.heappush(heap, (new_cost, v))

        # ── Build Result ──────────────────────────────────────────────────
        exec_ms = (time.perf_counter() - t_start) * 1000

        if best_shelter is None or math.isinf(best_cost):
            return RouteResult(
                path=[],
                destination=None,
                total_cost=math.inf,
                nodes_visited=nodes_visited,
                exec_time_ms=exec_ms,
                reachable=False,
                message="No safe route available — all shelters unreachable.",
            )

        # RECONSTRUCT PATH by walking predecessors backwards
        path: List[str] = []
        node: Optional[str] = best_shelter
        while node is not None:
            path.append(node)
            node = prev[node]
        path.reverse()          # Reverse to get start → … → shelter order

        node_info = self._nodes.get(best_shelter)
        shelter_label = node_info.label if node_info else best_shelter

        return RouteResult(
            path=path,
            destination=best_shelter,
            total_cost=round(best_cost, 2),
            nodes_visited=nodes_visited,
            exec_time_ms=round(exec_ms, 3),
            reachable=True,
            message=f"Route to {shelter_label}",
        )

    def dijkstra_no_hazard(self, start: str) -> RouteResult:
        """
        Run Dijkstra using base_weight only (ignoring hazards and blocks).
        Used for the 'Compare to Normal' overlay feature.
        """
        t_start = time.perf_counter()
        targets = self._shelters

        if start in targets:
            return RouteResult(path=[start], destination=start, total_cost=0.0,
                               nodes_visited=0,
                               exec_time_ms=(time.perf_counter() - t_start) * 1000,
                               reachable=True, message="Already at shelter")

        dist: Dict[str, float] = {n: math.inf for n in self._nodes}
        dist[start] = 0.0
        prev: Dict[str, Optional[str]] = {n: None for n in self._nodes}
        heap: List[Tuple[float, str]] = [(0.0, start)]
        finalized: set[str] = set()
        best_shelter: Optional[str] = None
        best_cost: float = math.inf

        while heap:
            cost, u = heapq.heappop(heap)
            if u in finalized:
                continue
            finalized.add(u)
            if u in targets:
                best_shelter = u
                best_cost = cost
                break
            for edge in self._adj.get(u, []):
                v = edge.to_node
                if v in finalized:
                    continue
                new_cost = cost + edge.base_weight   # ← base_weight, not effective
                if new_cost < dist[v]:
                    dist[v] = new_cost
                    prev[v] = u
                    heapq.heappush(heap, (new_cost, v))

        exec_ms = (time.perf_counter() - t_start) * 1000
        if best_shelter is None:
            return RouteResult(reachable=False, exec_time_ms=exec_ms,
                               message="No route (no-hazard baseline)")

        path: List[str] = []
        node: Optional[str] = best_shelter
        while node is not None:
            path.append(node)
            node = prev[node]
        path.reverse()
        return RouteResult(path=path, destination=best_shelter,
                           total_cost=round(best_cost, 2),
                           nodes_visited=len(finalized),
                           exec_time_ms=round(exec_ms, 3),
                           reachable=True, message="Baseline route")


# ─────────────────────────────────────────────────────────────────────────────
# GRAPH LOADER
# ─────────────────────────────────────────────────────────────────────────────

def load_graph_from_json(path: str | Path) -> Graph:
    """
    Load a Graph from a JSON file following the map_data.json schema.

    Handles:
      - FileNotFoundError  → raises with a friendly message
      - json.JSONDecodeError → raises with a friendly message
      - Missing keys       → raises KeyError with context

    Args:
        path: Path to the map_data.json file.

    Returns:
        A fully constructed Graph object ready for routing.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Map data file not found: {path}\n"
            "Ensure map_data.json is in the evacuation_router/ directory."
        )

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise json.JSONDecodeError(
            f"Invalid JSON in {path}: {exc.msg}", exc.doc, exc.pos
        ) from exc

    graph = Graph()
    graph.city_name = data.get("city_name", "Unknown City")

    # Load nodes
    shelters: set[str] = set(data.get("shelters", []))
    for n in data.get("nodes", []):
        ntype = "shelter" if n["id"] in shelters else n.get("type", "normal")
        graph.add_node(NodeInfo(
            node_id=n["id"],
            label=n["label"],
            x=float(n["x"]),
            y=float(n["y"]),
            node_type=ntype,
        ))

    # Load edges (bidirectional)
    for e in data.get("edges", []):
        graph.add_bidirectional_edge(
            edge_id=e["id"],
            from_id=e["from"],
            to_id=e["to"],
            weight=float(e["weight"]),
        )

    return graph
