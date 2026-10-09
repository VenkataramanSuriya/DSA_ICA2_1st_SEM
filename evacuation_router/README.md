# Urban Disaster Evacuation & Smart Traffic Router

> **DSA Final Project** — Production-quality emergency-operations dashboard built with Python 3.14 + CustomTkinter.  
> Computes real-time optimal evacuation routes on a dynamic city road network using Dijkstra's Algorithm.

---

## Overview

This application simulates an **emergency evacuation command center** for the fictional Rivermead District.  
When hazards or road blockages occur, it instantly recomputes the safest path to the nearest shelter using a binary min-heap priority queue implementation of Dijkstra's Algorithm.

### Key Features

| Feature | Description |
|---|---|
| **Dynamic map canvas** | Interactive city grid with color-coded roads and nodes |
| **One-click routing** | Click any node → instant route computation |
| **Hazard injection** | Left-click road = toggle blocked · Right-click = cycle 1×/2×/3× hazard |
| **Live re-routing** | Every map change triggers instant path recomputation |
| **Animated vehicle** | Traveling dot animates along the evacuation path |
| **Analytics panel** | Travel time, nodes visited, execution time, destination |
| **Path history log** | Timestamped scrollable history with Clear button |
| **Compare mode** | Toggle overlay of original (no-hazard) baseline route |
| **Export log** | Save full history to `.txt` file |
| **No-route handling** | Red banner if all shelters are unreachable |

---

## Installation & Run

### Prerequisites
- Python 3.10+ (tested on 3.14.7)
- `uv` package manager (or pip)

### Setup

```bash
# Clone / navigate to project
cd "DSA ICA 2/evacuation_router"

# Create virtual environment (from project root)
uv venv venv --python 3.14

# Install dependencies
uv pip install -r requirements.txt --python venv/Scripts/python.exe

# Run the application
venv\Scripts\python.exe main.py
```

### Run Tests

```bash
venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Expected output: **25 tests, 0 failures.**

---

## Project Structure

```
evacuation_router/
├── main.py          # Entry point — launches EvacuationApp
├── graph.py         # DSA layer: Edge, Graph, Dijkstra (ZERO UI imports)
├── ui.py            # View/Controller: dashboard, MapCanvas, panels
├── theme.py         # Color palette, fonts, spacing (single source of truth)
├── map_data.json    # Rivermead District city graph
├── tests/
│   └── test_graph.py  # 25 unit tests (unittest + Bellman-Ford oracle)
├── requirements.txt   # customtkinter only
└── README.md
```

---

## Controls

| Action | Control |
|---|---|
| **Set start node** | Left-click any intersection node |
| **Toggle road blocked** | Left-click a road or its weight label |
| **Cycle hazard (1×→2×→3×→1×)** | Right-click a road or its weight label |
| **Run Evacuation** | Click the blue "Run Evacuation" button |
| **Reset all hazards** | Click "Reset All Hazards" |
| **Toggle comparison route** | Check "Compare to Normal Route" |
| **Export log** | Click "Export Log" → choose save path |
| **View tooltip** | Hover over any road or node |

---

## Map: Rivermead District

12 intersections (A–L) arranged in a 4×3 grid:

```
A ─── B ─── C ─── D [SHELTER]
│     │     │     │
E ─── F ─── G ─── H
│     │     │     │
I ─── J ─── K ─── L
[S]       [S]
```

- **3 shelters:** D (top-right), I (bottom-left), K (bottom-center)
- **22 bidirectional roads** including diagonal cross-roads
- Road weights: 3–7 minutes base travel time

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  main.py  (entry point)                                  │
│     └── EvacuationApp (ui.py)                            │
│           ├── MapCanvas     ← interactive canvas widget  │
│           ├── AnalyticsCard ← stat cards                 │
│           ├── HistoryLog    ← scrollable log             │
│           └── Graph (graph.py)  ← pure DSA layer        │
│                 ├── NodeInfo / Edge (dataclasses)        │
│                 ├── dijkstra()   → RouteResult           │
│                 └── load_graph_from_json()               │
│  theme.py  (all colors/fonts — no widget code)          │
└─────────────────────────────────────────────────────────┘
```

**Separation of concerns:** `graph.py` has zero UI imports. The algorithmic layer is completely independent and testable in isolation.

---

## DSA Components

| Component | Implementation | Complexity |
|---|---|---|
| **Graph** | Adjacency List `Dict[str, List[Edge]]` | O(V + E) space |
| **Priority Queue** | Binary min-heap (`heapq`) | O(log V) push/pop |
| **Dijkstra** | Single-source, multi-destination | O((V+E) log V) time |
| **Edge weight** | `effective_weight()` = base × multiplier (∞ if blocked) | O(1) |
| **Path reconstruction** | Walk `prev[]` dict backwards | O(V) |

---

## Color Legend

| Color | Meaning |
|---|---|
| Gray road | Normal, unaffected |
| Yellow road | 2× hazard (slowed) |
| Orange road | 3× hazard (very slow) |
| Red dashed | Blocked (impassable) |
| Cyan/blue line | Active evacuation route |
| Faint blue dashed | Baseline comparison route |
| Green node | Emergency shelter |
| Amber node | Start node (with pulsing ring) |
