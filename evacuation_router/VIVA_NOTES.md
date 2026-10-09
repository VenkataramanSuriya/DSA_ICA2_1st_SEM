# VIVA NOTES — Urban Evacuation Router
## 15 Likely Examiner Questions & Answers

---

### Q1. Why did you choose an adjacency list over an adjacency matrix?

**Answer:** City graphs are *sparse* — most intersections connect to only 3–4 roads. An adjacency list uses O(V + E) space, while a matrix uses O(V²). For Rivermead with 12 nodes and 22 roads, the matrix wastes 67% of its 144 cells. More importantly, Dijkstra's inner loop only needs to visit *actual neighbors* — adjacency list does this in O(degree(v)) time vs O(V) for a matrix. For large cities (millions of intersections), the savings are enormous.

---

### Q2. Why use a heap (priority queue) instead of scanning all distances?

**Answer:** A binary min-heap always gives you the node with the smallest distance in O(log V) time. If you scan all V distances to find the minimum, that's O(V) per extraction — total O(V²) for the algorithm. The heap brings it down to O((V+E) log V). For sparse graphs, this is much faster: if E ≈ 4V (like our city), O((V + 4V) log V) = O(5V log V) vs O(V²). At V=10,000, that's 170,000 vs 100,000,000 operations.

---

### Q3. What is "edge relaxation"?

**Answer:** Edge relaxation is the core operation of Dijkstra. When we process node u, we look at every neighbor v connected by edge e. We check: is `dist[u] + weight(e)` less than our current best known distance to v? If yes, we've found a shorter path to v — so we *relax* (update) `dist[v]` and record u as v's predecessor. We then push the new (cost, v) onto the heap. It's called "relaxation" because we're tightening (reducing) an upper bound on the true shortest distance.

---

### Q4. Why does Dijkstra fail with negative edge weights?

**Answer:** Dijkstra relies on the greedy property: once a node is finalized, its distance is optimal. This only holds because with non-negative weights, no future path through unfinalized nodes can be *shorter* than what we already have. With negative edges, a later discovery like `u → w → v` with negative `w → v` could be cheaper even after v is finalized. Bellman-Ford handles this by relaxing all edges V-1 times, but runs in O(VE) time. Our system has no negative weights: base travel time ≥ 3 minutes, multiplier ≥ 1.0.

---

### Q5. How does hazard injection work without rebuilding the graph?

**Answer:** Each `Edge` object stores `base_weight` and `hazard_multiplier`. The `effective_weight()` method returns `base_weight × hazard_multiplier` (or ∞ if blocked). Dijkstra always calls `effective_weight()` — never the raw weight. So changing the multiplier (or setting blocked=True) on a road *immediately* affects the next Dijkstra run without touching the graph structure. This is O(1) for each hazard change.

---

### Q6. How do you find the best shelter without running Dijkstra multiple times?

**Answer:** This is the **multi-destination single-pass** technique. We run ONE Dijkstra from the start node. The heap extracts nodes in globally cost-sorted order. The moment we finalize a shelter node, it is provably the *globally nearest* shelter — because any path to a different shelter through an unfinalized node must cost at least as much. We stop immediately, returning that shelter's path. Time: O((V+E) log V) regardless of how many shelters there are.

---

### Q7. What does "stale entry skip" mean in your Dijkstra?

**Answer:** Python's `heapq` doesn't support efficient key-decrease, so when we find a shorter path to node v, we push a *new* (cheaper_cost, v) onto the heap — but the old (expensive_cost, v) entry stays there. When the old entry is eventually popped, we check: is v already in our `finalized` set? If yes, we skip it (it's stale). This doesn't affect correctness because we only act on the first finalization (which was the cheapest). It doesn't significantly affect complexity because each edge creates at most one heap push.

---

### Q8. What is the time complexity of your Dijkstra, and how do you derive it?

**Answer:** **O((V + E) log V)**.

Derivation:
- Each of V nodes is extracted from the heap exactly once: V pops × O(log V) = O(V log V)
- Each directed edge triggers at most one heap push when its source is finalized: E pushes × O(log V) = O(E log V)
- Total: O(V log V + E log V) = O((V + E) log V)

For Rivermead: V=12, E=44 (directed), so ≈ 56 × 3.58 ≈ 200 operations.

---

### Q9. What is the space complexity of the whole system?

**Answer:**
- **Adjacency list:** O(V + E) — V node entries, E total Edge objects
- **Dijkstra arrays** (dist, prev, finalized): O(V) each
- **Heap:** O(E) entries in worst case (one push per edge relaxation)
- **Total:** O(V + E) — dominated by the graph structure itself

---

### Q10. Why is your graph.py completely independent of the UI?

**Answer:** This is the **separation of concerns** principle. The algorithmic layer (graph.py) knows nothing about buttons, colors, or windows. This means:
1. The algorithm can be **unit tested** in isolation (no GUI needed)
2. The UI can be swapped (e.g., web frontend) without touching the algorithm
3. Multiple views can share the same graph object
4. Bugs in the UI don't corrupt algorithmic state

This is why all 25 unit tests run in 0.007 seconds with no window opened.

---

### Q11. How does path reconstruction work?

**Answer:** During Dijkstra, we maintain a `prev[v]` dictionary: `prev[v] = u` means "on the shortest path to v, we came from u". After finalizing the best shelter, we walk backwards: start at the shelter, follow `prev[]` links until we reach `None` (the start node), appending each node to a list. Then we reverse the list. This gives the path from start to shelter in O(V) time.

---

### Q12. What happens if the start node is itself a shelter?

**Answer:** We check this *before* running Dijkstra as a special case. If `start ∈ shelters`, we immediately return a RouteResult with `path=[start]`, `total_cost=0.0`, `nodes_visited=0`, and `message="Already at shelter"`. No pathfinding needed — cost is 0 and you're already safe. This is tested in `TestStartIsShelter`.

---

### Q13. What is the difference between base_weight and effective_weight?

**Answer:**
- **base_weight:** The default travel time under normal conditions (e.g., 4 minutes)
- **effective_weight():** The actual cost Dijkstra uses. If blocked → ∞. Otherwise → `base_weight × hazard_multiplier`. A 3× hazard on a 4-minute road makes it cost 12 minutes. Dijkstra never sees base_weight directly — it always calls effective_weight().

---

### Q14. How did you verify your Dijkstra is correct?

**Answer:** I implemented a **Bellman-Ford reference algorithm** in the test suite. Bellman-Ford is O(VE) — slower but provably correct. For every test scenario (baseline, hazard, block, all starting nodes, real map), I run both algorithms and assert that the destination shelter cost matches to 3 decimal places. If Dijkstra had a bug, the costs would differ. All 25 tests pass: `Ran 25 tests in 0.007s — OK`.

---

### Q15. How does the system handle the "no route" case?

**Answer:** If all shelters are unreachable (e.g., start node is fully isolated), Dijkstra exhausts the heap without ever finalizing a shelter. It returns `RouteResult(reachable=False, total_cost=math.inf, destination=None, path=[])`. The UI detects `result.reachable == False` and:
1. Shows a red banner: "⚠ No safe route available"
2. Updates the status chip to "✕ NO ROUTE"
3. Clears the route animation
4. Logs the failed attempt in history

No crash occurs — it's handled as a valid expected outcome, not an exception.
