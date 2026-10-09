/**
 * app.js — Complete Web Implementation of Dijkstra Evacuation Router
 * Zero external libraries: Pure JavaScript + HTML5 Canvas
 */

// ── Graph Data ──────────────────────────────────────────────────────────────
const MAP_DATA = {
  "city_name": "Rivermead District",
  "nodes": [
    {"id": "A", "label": "Apex Ave / 1st St",     "x": 120, "y": 100, "type": "normal"},
    {"id": "B", "label": "Brook Rd / 1st St",      "x": 320, "y": 100, "type": "normal"},
    {"id": "C", "label": "Crown St / 1st St",      "x": 520, "y": 100, "type": "normal"},
    {"id": "D", "label": "Delta Blvd / 1st St",    "x": 720, "y": 100, "type": "shelter"},
    {"id": "E", "label": "Apex Ave / 2nd St",      "x": 120, "y": 280, "type": "normal"},
    {"id": "F", "label": "Brook Rd / 2nd St",      "x": 320, "y": 280, "type": "normal"},
    {"id": "G", "label": "Crown St / 2nd St",      "x": 520, "y": 280, "type": "normal"},
    {"id": "H", "label": "Delta Blvd / 2nd St",    "x": 720, "y": 280, "type": "normal"},
    {"id": "I", "label": "Apex Ave / 3rd St",      "x": 120, "y": 460, "type": "shelter"},
    {"id": "J", "label": "Brook Rd / 3rd St",      "x": 320, "y": 460, "type": "normal"},
    {"id": "K", "label": "Crown St / 3rd St",      "x": 520, "y": 460, "type": "shelter"},
    {"id": "L", "label": "Delta Blvd / 3rd St",    "x": 720, "y": 460, "type": "normal"}
  ],
  "edges": [
    {"id": "e01", "from": "A", "to": "B", "weight": 4},
    {"id": "e02", "from": "B", "to": "C", "weight": 5},
    {"id": "e03", "from": "C", "to": "D", "weight": 3},
    {"id": "e04", "from": "A", "to": "E", "weight": 4},
    {"id": "e05", "from": "B", "to": "F", "weight": 4},
    {"id": "e06", "from": "C", "to": "G", "weight": 4},
    {"id": "e07", "from": "D", "to": "H", "weight": 4},
    {"id": "e08", "from": "E", "to": "F", "weight": 5},
    {"id": "e09", "from": "F", "to": "G", "weight": 4},
    {"id": "e10", "from": "G", "to": "H", "weight": 5},
    {"id": "e11", "from": "E", "to": "I", "weight": 4},
    {"id": "e12", "from": "F", "to": "J", "weight": 5},
    {"id": "e13", "from": "G", "to": "K", "weight": 4},
    {"id": "e14", "from": "H", "to": "L", "weight": 4},
    {"id": "e15", "from": "I", "to": "J", "weight": 4},
    {"id": "e16", "from": "J", "to": "K", "weight": 5},
    {"id": "e17", "from": "K", "to": "L", "weight": 3},
    {"id": "e18", "from": "A", "to": "F", "weight": 6},
    {"id": "e19", "from": "B", "to": "G", "weight": 6},
    {"id": "e20", "from": "F", "to": "K", "weight": 7},
    {"id": "e21", "from": "G", "to": "L", "weight": 6},
    {"id": "e22", "from": "C", "to": "H", "weight": 6}
  ],
  "shelters": ["D", "I", "K"]
};

// ── Binary Min-Heap Priority Queue ───────────────────────────────────────────
class MinHeap {
  constructor() {
    this.heap = [];
  }
  push(item) {
    this.heap.push(item);
    this._bubbleUp(this.heap.length - 1);
  }
  pop() {
    if (this.heap.length === 0) return null;
    const top = this.heap[0];
    const bottom = this.heap.pop();
    if (this.heap.length > 0) {
      this.heap[0] = bottom;
      this._bubbleDown(0);
    }
    return top;
  }
  isEmpty() {
    return this.heap.length === 0;
  }
  _bubbleUp(i) {
    while (i > 0) {
      const parent = Math.floor((i - 1) / 2);
      if (this.heap[i][0] < this.heap[parent][0]) {
        [this.heap[i], this.heap[parent]] = [this.heap[parent], this.heap[i]];
        i = parent;
      } else break;
    }
  }
  _bubbleDown(i) {
    const len = this.heap.length;
    while (true) {
      let left = 2 * i + 1;
      let right = 2 * i + 2;
      let smallest = i;
      if (left < len && this.heap[left][0] < this.heap[smallest][0]) smallest = left;
      if (right < len && this.heap[right][0] < this.heap[smallest][0]) smallest = right;
      if (smallest !== i) {
        [this.heap[i], this.heap[smallest]] = [this.heap[smallest], this.heap[i]];
        i = smallest;
      } else break;
    }
  }
}

// ── Graph Engine ─────────────────────────────────────────────────────────────
class Edge {
  constructor(id, from, to, baseWeight) {
    this.id = id;
    this.from = from;
    this.to = to;
    this.baseWeight = baseWeight;
    this.blocked = false;
    this.hazardMultiplier = 1.0;
  }
  effectiveWeight() {
    if (this.blocked) return Infinity;
    return this.baseWeight * this.hazardMultiplier;
  }
  cycleHazard() {
    if (this.hazardMultiplier < 1.5) this.hazardMultiplier = 2.0;
    else if (this.hazardMultiplier < 2.5) this.hazardMultiplier = 3.0;
    else this.hazardMultiplier = 1.0;
  }
  reset() {
    this.blocked = false;
    this.hazardMultiplier = 1.0;
  }
}

class Graph {
  constructor(data) {
    this.nodes = new Map();
    this.adj = new Map();
    this.edges = new Map();
    this.shelters = new Set(data.shelters);
    this.cityName = data.city_name;

    data.nodes.forEach(n => {
      this.nodes.set(n.id, { ...n, isShelter: this.shelters.has(n.id) });
      this.adj.set(n.id, []);
    });

    data.edges.forEach(e => {
      const edge = new Edge(e.id, e.from, e.to, e.weight);
      this.edges.set(e.id, edge);
      this.adj.get(e.from).push(edge);
      this.adj.get(e.to).push(edge);
    });
  }

  dijkstra(startId, useEffective = true) {
    const t0 = performance.now();
    if (this.shelters.has(startId)) {
      return {
        path: [startId],
        destination: startId,
        totalCost: 0,
        nodesVisited: 0,
        execTimeMs: +(performance.now() - t0).toFixed(3),
        reachable: true
      };
    }

    const dist = new Map();
    const prev = new Map();
    const finalized = new Set();
    this.nodes.forEach((_, id) => dist.set(id, Infinity));
    dist.set(startId, 0);

    const heap = new MinHeap();
    heap.push([0, startId]);

    let nodesVisited = 0;
    let bestShelter = null;
    let bestCost = Infinity;

    while (!heap.isEmpty()) {
      const [cost, u] = heap.pop();
      if (finalized.has(u)) continue;
      finalized.add(u);
      nodesVisited++;

      if (this.shelters.has(u)) {
        bestShelter = u;
        bestCost = cost;
        break;
      }

      for (const edge of this.adj.get(u)) {
        const v = edge.from === u ? edge.to : edge.from;
        if (finalized.has(v)) continue;

        const w = useEffective ? edge.effectiveWeight() : edge.baseWeight;
        if (w === Infinity) continue;

        const newCost = cost + w;
        if (newCost < dist.get(v)) {
          dist.set(v, newCost);
          prev.set(v, u);
          heap.push([newCost, v]);
        }
      }
    }

    const execTimeMs = +(performance.now() - t0).toFixed(3);
    if (!bestShelter || bestCost === Infinity) {
      return {
        path: [],
        destination: null,
        totalCost: Infinity,
        nodesVisited,
        execTimeMs,
        reachable: false
      };
    }

    const path = [];
    let curr = bestShelter;
    while (curr) {
      path.push(curr);
      curr = prev.get(curr);
    }
    path.reverse();

    return {
      path,
      destination: bestShelter,
      totalCost: bestCost,
      nodesVisited,
      execTimeMs,
      reachable: true
    };
  }
}

// ── Application UI & Controller ──────────────────────────────────────────────
const graph = new Graph(MAP_DATA);
let startNodeId = null;
let currentRoute = null;
let compareRoute = null;
let showCompare = false;
let historyLog = [];

// Canvas setup
const canvas = document.getElementById("mapCanvas");
const ctx = canvas.getContext("2d");
const tooltip = document.getElementById("tooltip");

let scale = 1.0;
let offsetX = 0;
let offsetY = 0;
let vehicleProgress = 0;
let animationFrameId = null;

function resizeCanvas() {
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width * window.devicePixelRatio;
  canvas.height = rect.height * window.devicePixelRatio;
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
  computeTransform(rect.width, rect.height);
  draw();
}

function computeTransform(w, h) {
  const margin = 60;
  const xs = Array.from(graph.nodes.values()).map(n => n.x);
  const ys = Array.from(graph.nodes.values()).map(n => n.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);

  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);

  const availW = Math.max(w - 2 * margin, 1);
  const availH = Math.max(h - 2 * margin, 1);

  scale = Math.min(availW / spanX, availH / spanY);
  offsetX = margin + (availW - spanX * scale) / 2 - minX * scale;
  offsetY = margin + (availH - spanY * scale) / 2 - minY * scale;
}

function getNodePos(nodeId) {
  const node = graph.nodes.get(nodeId);
  return {
    x: node.x * scale + offsetX,
    y: node.y * scale + offsetY
  };
}

// ── Drawing Routines ─────────────────────────────────────────────────────────
function draw() {
  const w = canvas.width / window.devicePixelRatio;
  const h = canvas.height / window.devicePixelRatio;

  ctx.clearRect(0, 0, w, h);
  drawGrid(w, h);
  drawEdges();
  if (showCompare && compareRoute && compareRoute.path.length > 1) {
    drawComparePath(compareRoute.path);
  }
  if (currentRoute && currentRoute.path.length > 1) {
    drawRouteGlow(currentRoute.path);
  }
  drawNodes();
  if (currentRoute && currentRoute.path.length > 1) {
    drawVehicle(currentRoute.path);
  }
}

function drawGrid(w, h) {
  ctx.strokeStyle = "#1c1f2e";
  ctx.lineWidth = 1;
  const step = 40;
  for (let x = 0; x < w; x += step) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }
  for (let y = 0; y < h; y += step) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
}

function drawEdges() {
  graph.edges.forEach(edge => {
    const p1 = getNodePos(edge.from);
    const p2 = getNodePos(edge.to);

    let color = "#4a4e6a";
    let width = 3;
    if (edge.blocked) {
      color = "#ea4335";
    } else if (edge.hazardMultiplier >= 2.5) {
      color = "#ff6d00";
      width = 4;
    } else if (edge.hazardMultiplier >= 1.5) {
      color = "#f4b400";
      width = 4;
    }

    ctx.save();
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.lineCap = "round";
    if (edge.blocked) ctx.setLineDash([6, 5]);
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.stroke();
    ctx.restore();

    // Weight label
    const mx = (p1.x + p2.x) / 2;
    const my = (p1.y + p2.y) / 2;
    ctx.fillStyle = "#9aa0a6";
    ctx.font = "bold 9px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    const label = edge.blocked ? "✖" : (edge.hazardMultiplier > 1 ? `${edge.effectiveWeight()}m` : `${edge.baseWeight}m`);
    ctx.fillText(label, mx, my - 6);
  });
}

function drawComparePath(path) {
  ctx.save();
  ctx.strokeStyle = "#4c8dff";
  ctx.lineWidth = 2;
  ctx.setLineDash([8, 6]);
  ctx.beginPath();
  for (let i = 0; i < path.length; i++) {
    const p = getNodePos(path[i]);
    if (i === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  }
  ctx.stroke();
  ctx.restore();
}

function drawRouteGlow(path) {
  // Glow underlay
  ctx.save();
  ctx.strokeStyle = "#004c6e";
  ctx.lineWidth = 12;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  path.forEach((id, i) => {
    const p = getNodePos(id);
    if (i === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  });
  ctx.stroke();

  // Cyan bright line
  ctx.strokeStyle = "#00d4ff";
  ctx.lineWidth = 5;
  ctx.stroke();
  ctx.restore();
}

function drawNodes() {
  const routeSet = new Set(currentRoute ? currentRoute.path : []);

  graph.nodes.forEach((node, id) => {
    const p = getNodePos(id);
    const isStart = id === startNodeId;
    const isShelter = node.isShelter;
    const onRoute = routeSet.has(id);

    let radius = isShelter ? 20 : 16;
    let fill = "#2a3050";
    let border = "#4a4e6a";
    let borderWidth = 2;

    if (isShelter) {
      fill = "#1a4a2e";
      border = "#34a853";
      borderWidth = 2.5;
    } else if (isStart) {
      fill = "#5a3e00";
      border = "#f4b400";
      borderWidth = 3;
    }

    if (onRoute) {
      border = "#00d4ff";
      borderWidth = 3;
    }

    // Outer glow for start node
    if (isStart) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, radius + 8, 0, Math.PI * 2);
      ctx.strokeStyle = "#f4b400";
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    // Node body
    ctx.beginPath();
    ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = border;
    ctx.lineWidth = borderWidth;
    ctx.stroke();

    // Node text
    ctx.fillStyle = "#e8eaed";
    ctx.font = "bold 11px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(id, p.x, isShelter ? p.y - 4 : p.y);

    if (isShelter) {
      ctx.fillStyle = "#34a853";
      ctx.font = "bold 10px Inter, sans-serif";
      ctx.fillText("✚", p.x, p.y + 8);
    }

    // Label under node
    ctx.fillStyle = "#9aa0a6";
    ctx.font = "9px Inter, sans-serif";
    ctx.fillText(node.label.split("/")[0].trim(), p.x, p.y + radius + 14);
  });
}

function drawVehicle(path) {
  const coords = path.map(getNodePos);
  const totalSegments = coords.length - 1;
  const currentSeg = Math.min(Math.floor(vehicleProgress), totalSegments - 1);
  const t = vehicleProgress - currentSeg;

  const p1 = coords[currentSeg];
  const p2 = coords[currentSeg + 1];
  const vx = p1.x + (p2.x - p1.x) * t;
  const vy = p1.y + (p2.y - p1.y) * t;

  ctx.beginPath();
  ctx.arc(vx, vy, 7, 0, Math.PI * 2);
  ctx.fillStyle = "#00d4ff";
  ctx.fill();
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 2;
  ctx.stroke();
}

function animate() {
  if (currentRoute && currentRoute.path.length > 1) {
    vehicleProgress += 0.025;
    if (vehicleProgress >= currentRoute.path.length - 1) {
      vehicleProgress = 0;
    }
    draw();
  }
  animationFrameId = requestAnimationFrame(animate);
}

// ── Routing & State Updates ──────────────────────────────────────────────────
function runEvacuation() {
  if (!startNodeId) {
    setStatusBar("Please click an intersection node to set origin.");
    return;
  }

  document.getElementById("statusChip").className = "status-chip chip-reroute";
  document.getElementById("statusChip").innerText = "⟳ REROUTING";

  currentRoute = graph.dijkstra(startNodeId, true);
  compareRoute = graph.dijkstra(startNodeId, false);
  vehicleProgress = 0;

  const banner = document.getElementById("noRouteBanner");
  if (currentRoute.reachable) {
    document.getElementById("statusChip").className = "status-chip chip-active";
    document.getElementById("statusChip").innerText = "● ROUTE ACTIVE";
    banner.style.display = "none";

    document.getElementById("valTime").innerText = `${currentRoute.totalCost} min`;
    document.getElementById("valDest").innerText = `Shelter ${currentRoute.destination}`;
    document.getElementById("valVisited").innerText = currentRoute.nodesVisited;
    document.getElementById("valExec").innerText = `${currentRoute.execTimeMs} ms`;
    document.getElementById("valPath").innerText = currentRoute.path.join(" → ");

    addHistoryEntry(startNodeId, currentRoute);
  } else {
    document.getElementById("statusChip").className = "status-chip chip-noroute";
    document.getElementById("statusChip").innerText = "✕ NO ROUTE";
    banner.style.display = "flex";

    document.getElementById("valTime").innerText = "∞";
    document.getElementById("valDest").innerText = "None";
    document.getElementById("valVisited").innerText = currentRoute.nodesVisited;
    document.getElementById("valExec").innerText = `${currentRoute.execTimeMs} ms`;
    document.getElementById("valPath").innerText = "No reachable shelter";

    addHistoryEntry(startNodeId, currentRoute);
  }
  draw();
}

function addHistoryEntry(start, route) {
  const ts = new Date().toLocaleTimeString();
  const box = document.getElementById("historyBox");
  const item = document.createElement("div");
  item.className = `log-item ${route.reachable ? "" : "fail"}`;

  if (route.reachable) {
    item.innerHTML = `
      <div class="log-time">[${ts}] ${start} → ${route.destination}</div>
      <div class="log-route">${route.path.join(" → ")}</div>
      <div class="log-stats">Cost: ${route.totalCost} min | Visited: ${route.nodesVisited} | ${route.execTimeMs} ms</div>
    `;
  } else {
    item.innerHTML = `
      <div class="log-time">[${ts}] ${start} → NO ROUTE</div>
      <div class="log-stats" style="color:var(--danger)">All shelters unreachable</div>
    `;
  }

  box.prepend(item);
  historyLog.unshift(`[${ts}] ${start} → ${route.destination || 'NO ROUTE'} | Cost: ${route.totalCost} min | Visited: ${route.nodesVisited} | ${route.path.join(' -> ')}`);
}

function setStatusBar(msg) {
  document.getElementById("statusBar").innerText = `ℹ ${msg}`;
}

// ── Hit Testing & Interactions ───────────────────────────────────────────────
function hitTestNode(mx, my) {
  for (const [id, node] of graph.nodes) {
    const p = getNodePos(id);
    const dist = Math.hypot(p.x - mx, p.y - my);
    if (dist <= 24) return id;
  }
  return null;
}

function hitTestEdge(mx, my) {
  for (const [id, edge] of graph.edges) {
    const p1 = getNodePos(edge.from);
    const p2 = getNodePos(edge.to);
    const d = distToSegment({ x: mx, y: my }, p1, p2);
    if (d <= 14) return id;
  }
  return null;
}

function distToSegment(p, v, w) {
  const l2 = (v.x - w.x) ** 2 + (v.y - w.y) ** 2;
  if (l2 === 0) return Math.hypot(p.x - v.x, p.y - v.y);
  let t = ((p.x - v.x) * (w.x - v.x) + (p.y - v.y) * (w.y - v.y)) / l2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(p.x - (v.x + t * (w.x - v.x)), p.y - (v.y + t * (w.y - v.y)));
}

// ── Event Listeners ──────────────────────────────────────────────────────────
canvas.addEventListener("click", e => {
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;

  const nid = hitTestNode(mx, my);
  if (nid) {
    startNodeId = nid;
    const node = graph.nodes.get(nid);
    document.getElementById("startNodeDisplay").innerText = `Node ${nid} — ${node.label.split('/')[0]}`;
    setStatusBar(`Origin set to Intersection ${nid}. Computing optimal evacuation route.`);
    runEvacuation();
    return;
  }

  const eid = hitTestEdge(mx, my);
  if (eid) {
    const edge = graph.edges.get(eid);
    edge.blocked = !edge.blocked;
    setStatusBar(`Road ${edge.from} ↔ ${edge.to} ${edge.blocked ? 'BLOCKED' : 'OPENED'}. Rerouting...`);
    if (startNodeId) runEvacuation();
    else draw();
  }
});

canvas.addEventListener("contextmenu", e => {
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;

  const eid = hitTestEdge(mx, my);
  if (eid) {
    const edge = graph.edges.get(eid);
    edge.cycleHazard();
    setStatusBar(`Road ${edge.from} ↔ ${edge.to} hazard set to ${edge.hazardMultiplier}×. Rerouting...`);
    if (startNodeId) runEvacuation();
    else draw();
  }
});

canvas.addEventListener("mousemove", e => {
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;

  const nid = hitTestNode(mx, my);
  if (nid) {
    const node = graph.nodes.get(nid);
    tooltip.style.display = "block";
    tooltip.style.left = `${e.clientX + 14}px`;
    tooltip.style.top = `${e.clientY + 14}px`;
    tooltip.innerText = `Intersection ${nid}\n${node.label}\n${node.isShelter ? '🏥 EMERGENCY SHELTER' : 'Road Junction'}`;
    return;
  }

  const eid = hitTestEdge(mx, my);
  if (eid) {
    const edge = graph.edges.get(eid);
    tooltip.style.display = "block";
    tooltip.style.left = `${e.clientX + 14}px`;
    tooltip.style.top = `${e.clientY + 14}px`;
    tooltip.innerText = `Road ${edge.from} ↔ ${edge.to}\nBase Weight: ${edge.baseWeight} min\nHazard: ${edge.hazardMultiplier}×\nEffective: ${edge.blocked ? 'BLOCKED (∞)' : edge.effectiveWeight() + ' min'}\n[Left Click]: Toggle Block\n[Right Click]: Cycle Hazard`;
    return;
  }

  tooltip.style.display = "none";
});

canvas.addEventListener("mouseleave", () => {
  tooltip.style.display = "none";
});

// Controls
document.getElementById("btnRun").addEventListener("click", runEvacuation);
document.getElementById("btnReset").addEventListener("click", () => {
  graph.edges.forEach(e => e.reset());
  setStatusBar("All road hazards and blockages reset to normal.");
  if (startNodeId) runEvacuation();
  else draw();
});

document.getElementById("chkCompare").addEventListener("change", e => {
  showCompare = e.target.checked;
  draw();
});

document.getElementById("btnClearLog").addEventListener("click", () => {
  document.getElementById("historyBox").innerHTML = "";
  historyLog = [];
});

document.getElementById("btnExport").addEventListener("click", () => {
  if (historyLog.length === 0) {
    alert("No history log entries to export.");
    return;
  }
  const blob = new Blob([historyLog.join("\n")], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `evacuation_log_${Date.now()}.txt`;
  a.click();
  URL.revokeObjectURL(url);
});

window.addEventListener("resize", resizeCanvas);

// Initial start
resizeCanvas();
animate();
