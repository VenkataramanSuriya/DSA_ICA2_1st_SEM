"""
ui.py — View / Controller layer for the Urban Evacuation Router dashboard.

Imports: CustomTkinter (with tkinter fallback), tkinter.Canvas, theme.py, graph.py.
No algorithm logic lives here — all routing is delegated to Graph / RouteResult.
"""

from __future__ import annotations

import json
import math
import os
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.messagebox as mb
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
except ImportError:
    CTK_AVAILABLE = False

import theme as T
from graph import Edge, Graph, NodeInfo, RouteResult, load_graph_from_json

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _hex_to_rgb(h: str) -> Tuple[int, int, int]:
    """Convert '#rrggbb' hex string to (r, g, b) integers."""
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert (r, g, b) integers to '#rrggbb' hex string."""
    return f"#{r:02x}{g:02x}{b:02x}"


def _lerp_color(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two hex colors at fraction t ∈ [0, 1]."""
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return _rgb_to_hex(r, g, b)


def _make_frame(parent: tk.Widget, bg: str, **kwargs) -> tk.Frame:
    """Create a plain tk.Frame with specified background."""
    return tk.Frame(parent, bg=bg, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# TOOLTIP
# ─────────────────────────────────────────────────────────────────────────────

class Tooltip:
    """
    Hover tooltip for Canvas items.
    Appears ~500 ms after hovering and disappears when the cursor moves away.
    """

    _DELAY_MS = 500

    def __init__(self, canvas: tk.Canvas) -> None:
        self._canvas = canvas
        self._win: Optional[tk.Toplevel] = None
        self._after_id: Optional[str] = None

    def show(self, text: str, x_screen: int, y_screen: int) -> None:
        """Schedule tooltip to appear."""
        self.hide()
        self._after_id = self._canvas.after(
            self._DELAY_MS,
            lambda: self._create(text, x_screen, y_screen),
        )

    def _create(self, text: str, x: int, y: int) -> None:
        self.hide()
        self._win = tk.Toplevel(self._canvas)
        self._win.wm_overrideredirect(True)
        self._win.wm_geometry(f"+{x + 16}+{y + 16}")
        lbl = tk.Label(
            self._win,
            text=text,
            bg="#1a1d27",
            fg=T.TEXT_PRIMARY,
            font=T.FONT_TOOLTIP,
            relief="flat",
            bd=0,
            padx=8,
            pady=4,
        )
        lbl.pack()

    def hide(self) -> None:
        """Cancel pending tooltip and destroy any visible tooltip window."""
        if self._after_id:
            self._canvas.after_cancel(self._after_id)
            self._after_id = None
        if self._win:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None


# ─────────────────────────────────────────────────────────────────────────────
# MAP CANVAS WIDGET
# ─────────────────────────────────────────────────────────────────────────────

class MapCanvas(tk.Canvas):
    """
    Interactive city-map canvas.

    Responsibilities:
      - Draw grid background, roads (color-coded by state), nodes (color-coded by role).
      - Handle left-click (set start / toggle block) and right-click (cycle hazard).
      - Animate the evacuation route (segment-by-segment draw + traveling vehicle dot).
      - Fade road colors on state change.
      - Show hover tooltips.
      - Accept callbacks for interaction events.
    """

    # Padding around the map content inside the canvas
    _MARGIN = 60

    def __init__(self, parent: tk.Widget, graph: Graph, **kwargs) -> None:
        kwargs.setdefault("bg", T.MAP_BG)
        super().__init__(
            parent,
            highlightthickness=0,
            **kwargs,
        )
        self._graph = graph
        self._tooltip = Tooltip(self)

        # State
        self._start_node: Optional[str] = None
        self._route_path: List[str] = []
        self._compare_path: List[str] = []
        self._show_compare: bool = False

        # Scale/offset for fitting map nodes into canvas
        self._scale: float = 1.0
        self._offset_x: float = 0.0
        self._offset_y: float = 0.0

        # Callbacks (set by EvacuationApp)
        self.on_start_changed: Optional[Callable[[str], None]] = None
        self.on_edge_blocked: Optional[Callable[[str], None]] = None
        self.on_edge_hazard: Optional[Callable[[str], None]] = None

        # Animation state
        self._anim_after_id: Optional[str] = None
        self._vehicle_id: Optional[int] = None
        self._vehicle_path_coords: List[Tuple[float, float]] = []
        self._vehicle_seg_idx: int = 0
        self._vehicle_t: float = 0.0

        # Color fade tracking: edge_id → current color
        self._edge_colors: Dict[str, str] = {}
        self._fade_jobs: Dict[str, str] = {}  # edge_id → after_id

        # Canvas item IDs
        self._node_items: Dict[str, Dict[str, int]] = {}   # node_id → {circle, text, glow}
        self._edge_items: Dict[str, Dict[str, int]] = {}   # edge_id → {glow, line, label}

        # Bind resize
        self.bind("<Configure>", self._on_resize)
        # Bind mouse
        self.bind("<Button-1>", self._on_left_click)
        self.bind("<Button-3>", self._on_right_click)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _: self._tooltip.hide())

        # Initial draw after layout
        self.after(100, self._full_redraw)

    # ── Layout ────────────────────────────────────────────────────────────

    def _compute_transform(self) -> None:
        """Compute scale + offset to fit all node coordinates into the canvas."""
        nodes = self._graph.get_all_nodes()
        if not nodes:
            self._scale = 1.0
            self._offset_x = 0.0
            self._offset_y = 0.0
            return

        xs = [n.x for n in nodes.values()]
        ys = [n.y for n in nodes.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        cw = self.winfo_width()
        ch = self.winfo_height()
        avail_w = max(cw - 2 * self._MARGIN, 1)
        avail_h = max(ch - 2 * self._MARGIN, 1)

        span_x = max(max_x - min_x, 1)
        span_y = max(max_y - min_y, 1)
        self._scale = min(avail_w / span_x, avail_h / span_y)

        # Center the scaled content
        scaled_w = span_x * self._scale
        scaled_h = span_y * self._scale
        self._offset_x = self._MARGIN + (avail_w - scaled_w) / 2 - min_x * self._scale
        self._offset_y = self._MARGIN + (avail_h - scaled_h) / 2 - min_y * self._scale

    def _node_canvas_pos(self, node_id: str) -> Tuple[float, float]:
        """Return canvas (x, y) for a node's center."""
        n = self._graph.get_node(node_id)
        if n is None:
            return (0.0, 0.0)
        return (
            n.x * self._scale + self._offset_x,
            n.y * self._scale + self._offset_y,
        )

    def _on_resize(self, _event: tk.Event) -> None:
        self.after_idle(self._full_redraw)

    # ── Full Redraw ───────────────────────────────────────────────────────

    def _full_redraw(self) -> None:
        """Clear and redraw every element on the canvas."""
        self.delete("all")
        self._node_items.clear()
        self._edge_items.clear()
        self._vehicle_id = None
        self._compute_transform()
        self._draw_grid()
        self._draw_all_edges()
        if self._show_compare and self._compare_path:
            self._draw_compare_path()
        if self._route_path:
            self._draw_route_segments()
        self._draw_all_nodes()
        self._draw_legend()

    # ── Grid ──────────────────────────────────────────────────────────────

    def _draw_grid(self) -> None:
        """Draw a subtle background grid."""
        cw = self.winfo_width()
        ch = self.winfo_height()
        step = 40
        for x in range(0, cw, step):
            self.create_line(x, 0, x, ch, fill=T.MAP_GRID, width=1, tags="grid")
        for y in range(0, ch, step):
            self.create_line(0, y, cw, y, fill=T.MAP_GRID, width=1, tags="grid")

    # ── Edges ─────────────────────────────────────────────────────────────

    def _edge_color(self, edge_id: str) -> str:
        """Determine the road color based on current edge state."""
        pair = self._graph.get_edge_pair(edge_id)
        if pair is None:
            return T.ROAD_NORMAL
        fwd = pair[0]
        if fwd.blocked:
            return T.ROAD_BLOCKED
        if fwd.hazard_multiplier >= 2.5:
            return T.ROAD_HAZARD3
        if fwd.hazard_multiplier >= 1.5:
            return T.ROAD_HAZARD2
        return T.ROAD_NORMAL

    def _edge_width(self, edge_id: str) -> int:
        """Road line width scales with severity."""
        pair = self._graph.get_edge_pair(edge_id)
        if pair is None:
            return T.ROAD_WIDTH_NORMAL
        fwd = pair[0]
        if fwd.blocked:
            return T.ROAD_WIDTH_BLOCKED
        if fwd.hazard_multiplier > 1.0:
            return T.ROAD_WIDTH_HAZARD
        return T.ROAD_WIDTH_NORMAL

    def _draw_all_edges(self) -> None:
        """Draw every road on the canvas."""
        route_set: set[Tuple[str, str]] = set()
        if self._route_path:
            for i in range(len(self._route_path) - 1):
                a, b = self._route_path[i], self._route_path[i + 1]
                route_set.add((a, b))
                route_set.add((b, a))

        for eid, (fwd, _bwd) in self._graph.get_all_edge_pairs().items():
            x1, y1 = self._node_canvas_pos(fwd.from_node)
            x2, y2 = self._node_canvas_pos(fwd.to_node)

            color = self._edge_color(eid)
            width = self._edge_width(eid)
            dash = (6, 4) if fwd.blocked else None

            # Glow underlay (only for normal/hazard roads not on route)
            glow_id = self.create_line(
                x1, y1, x2, y2,
                fill=color,
                width=width + 4,
                tags=("edge_glow", f"eg_{eid}"),
                capstyle=tk.ROUND,
            )
            self.itemconfig(glow_id, stipple="gray25")

            # Main road line
            kw: Dict = dict(
                fill=color,
                width=width,
                tags=("edge", f"e_{eid}"),
                capstyle=tk.ROUND,
            )
            if dash:
                kw["dash"] = dash
            line_id = self.create_line(x1, y1, x2, y2, **kw)

            # Midpoint label (weight text)
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            pair = self._graph.get_edge_pair(eid)
            lbl_text = ""
            if pair:
                ef = pair[0].effective_weight()
                if math.isinf(ef):
                    lbl_text = "✖"
                elif pair[0].hazard_multiplier != 1.0:
                    lbl_text = f"{ef:.0f}m"
                else:
                    lbl_text = f"{pair[0].base_weight:.0f}m"

            lbl_id = self.create_text(
                mx, my - 10,
                text=lbl_text,
                fill=T.TEXT_MUTED,
                font=T.FONT_NODE_LABEL,
                tags=("edge_lbl", f"el_{eid}"),
            )

            self._edge_items[eid] = {
                "glow": glow_id,
                "line": line_id,
                "label": lbl_id,
            }
            self._edge_colors[eid] = color

            # Bind clicks/hover to ALL edge items (topmost-item problem solved by tagging)
            for item_id in (glow_id, line_id, lbl_id):
                self.tag_bind(
                    item_id, "<Button-1>",
                    lambda e, eid=eid: self._edge_left_click(eid, e),
                )
                self.tag_bind(
                    item_id, "<Button-3>",
                    lambda e, eid=eid: self._edge_right_click(eid, e),
                )
                self.tag_bind(
                    item_id, "<Enter>",
                    lambda e, eid=eid: self._edge_hover_enter(eid, e),
                )
                self.tag_bind(
                    item_id, "<Leave>",
                    lambda _e: self._tooltip.hide(),
                )

    def _redraw_edge(self, edge_id: str) -> None:
        """Update a single edge's visual after a state change."""
        items = self._edge_items.get(edge_id)
        if not items:
            return
        color = self._edge_color(edge_id)
        width = self._edge_width(edge_id)
        pair = self._graph.get_edge_pair(edge_id)
        fwd = pair[0] if pair else None
        dash = (6, 4) if (fwd and fwd.blocked) else ()

        old_color = self._edge_colors.get(edge_id, color)
        self._fade_edge(edge_id, old_color, color, items["line"], items["glow"])

        # Width + dash
        cfg: Dict = dict(width=width)
        if dash:
            cfg["dash"] = dash
        else:
            cfg["dash"] = ""
        self.itemconfig(items["line"], **cfg)
        self.itemconfig(items["glow"], width=width + 4)

        # Update label
        if pair:
            ef = pair[0].effective_weight()
            if math.isinf(ef):
                lbl = "✖"
            elif pair[0].hazard_multiplier != 1.0:
                lbl = f"{ef:.0f}m"
            else:
                lbl = f"{pair[0].base_weight:.0f}m"
            self.itemconfig(items["label"], text=lbl)

    def _fade_edge(
        self,
        eid: str,
        from_color: str,
        to_color: str,
        line_id: int,
        glow_id: int,
    ) -> None:
        """Animate a color transition over ANIM_FADE_MS milliseconds."""
        # Cancel any pending fade for this edge
        old_job = self._fade_jobs.get(eid)
        if old_job:
            try:
                self.after_cancel(old_job)
            except Exception:
                pass

        steps = T.ANIM_STEPS
        interval = T.ANIM_FADE_MS // steps

        def step(i: int) -> None:
            t = i / steps
            c = _lerp_color(from_color, to_color, t)
            try:
                self.itemconfig(line_id, fill=c)
                self.itemconfig(glow_id, fill=c)
            except Exception:
                return
            if i < steps:
                jid = self.after(interval, lambda: step(i + 1))
                self._fade_jobs[eid] = jid
            else:
                self._edge_colors[eid] = to_color
                self._fade_jobs.pop(eid, None)

        step(0)

    # ── Nodes ─────────────────────────────────────────────────────────────

    def _draw_all_nodes(self) -> None:
        """Draw every node (intersection) on top of the roads."""
        route_set: set[str] = set(self._route_path)
        for nid, info in self._graph.get_all_nodes().items():
            self._draw_node(nid, info, nid in route_set)

    def _draw_node(self, nid: str, info: NodeInfo, on_route: bool) -> None:
        """Draw a single node circle + label."""
        cx, cy = self._node_canvas_pos(nid)
        r = T.NODE_RADIUS
        is_shelter = info.is_shelter
        is_start = nid == self._start_node

        if is_shelter:
            r += T.NODE_SHELTER_EXTRA
            fill = T.NODE_SHELTER
            border = T.NODE_SHELTER_BRD
            border_w = 2
        elif is_start:
            fill = T.NODE_START
            border = T.NODE_START_BRD
            border_w = 3
        else:
            fill = T.NODE_NORMAL
            border = T.NODE_BORDER
            border_w = 1

        if on_route:
            border = T.NODE_ROUTE_HL
            border_w = 3

        # Outer glow for start node
        if is_start:
            glow_id = self.create_oval(
                cx - r - 8, cy - r - 8,
                cx + r + 8, cy + r + 8,
                outline=T.NODE_START_BRD,
                width=2,
                fill="",
                tags=("node_glow", f"ng_{nid}"),
            )
        else:
            glow_id = None

        # Node circle
        oval_id = self.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=fill,
            outline=border,
            width=border_w,
            tags=("node", f"n_{nid}"),
        )

        # Node ID label (inside circle)
        id_id = self.create_text(
            cx, cy - 3,
            text=nid,
            fill=T.NODE_TEXT,
            font=(T.FONT_FAMILY, 10, "bold"),
            tags=("node_lbl", f"nl_{nid}"),
        )

        # Shelter icon (+)
        if is_shelter:
            self.create_text(
                cx, cy + 9,
                text="✚",
                fill=T.NODE_SHELTER_BRD,
                font=(T.FONT_FAMILY, 9),
                tags=("shelter_icon", f"si_{nid}"),
            )

        # Road name below node
        name_id = self.create_text(
            cx, cy + r + 12,
            text=info.label.split("/")[0].strip(),
            fill=T.TEXT_MUTED,
            font=T.FONT_HEADER_NODE,
            tags=("node_name", f"nn_{nid}"),
        )

        items: Dict[str, int] = {"oval": oval_id, "id_text": id_id, "name": name_id}
        if glow_id is not None:
            items["glow"] = glow_id
        self._node_items[nid] = items

        # Bind clicks and hover
        for item_id in [oval_id, id_id]:
            self.tag_bind(
                item_id, "<Button-1>",
                lambda e, nid=nid: self._node_left_click(nid, e),
            )
            self.tag_bind(
                item_id, "<Enter>",
                lambda e, nid=nid: self._node_hover_enter(nid, e),
            )
            self.tag_bind(
                item_id, "<Leave>",
                lambda _e: self._tooltip.hide(),
            )

    # ── Route Drawing ─────────────────────────────────────────────────────

    def _draw_route_segments(self) -> None:
        """Draw the active evacuation route with glow effect."""
        if len(self._route_path) < 2:
            return
        coords: List[Tuple[float, float]] = []
        for nid in self._route_path:
            coords.append(self._node_canvas_pos(nid))

        for i in range(len(coords) - 1):
            x1, y1 = coords[i]
            x2, y2 = coords[i + 1]
            # Glow underlay
            self.create_line(
                x1, y1, x2, y2,
                fill=T.ROAD_ROUTE_GLOW,
                width=T.ROAD_WIDTH_GLOW,
                capstyle=tk.ROUND,
                tags="route_glow",
            )
            # Bright route line
            self.create_line(
                x1, y1, x2, y2,
                fill=T.ROAD_ROUTE,
                width=T.ROAD_WIDTH_ROUTE,
                capstyle=tk.ROUND,
                tags="route_line",
            )

        # Raise route above roads
        self.tag_raise("route_glow")
        self.tag_raise("route_line")
        self.tag_raise("node_glow")
        self.tag_raise("node")
        self.tag_raise("node_lbl")
        self.tag_raise("shelter_icon")
        self.tag_raise("node_name")

    def _draw_compare_path(self) -> None:
        """Draw the baseline (no-hazard) route as a faint dashed line."""
        if len(self._compare_path) < 2:
            return
        for i in range(len(self._compare_path) - 1):
            x1, y1 = self._node_canvas_pos(self._compare_path[i])
            x2, y2 = self._node_canvas_pos(self._compare_path[i + 1])
            self.create_line(
                x1, y1, x2, y2,
                fill=T.ROAD_COMPARE,
                width=2,
                dash=(8, 5),
                capstyle=tk.ROUND,
                tags="compare_line",
            )

    # ── Animated Vehicle ──────────────────────────────────────────────────

    def animate_vehicle(self) -> None:
        """Start the vehicle animation along the current route."""
        if len(self._route_path) < 2:
            return
        self._stop_vehicle()
        self._vehicle_path_coords = [
            self._node_canvas_pos(nid) for nid in self._route_path
        ]
        self._vehicle_seg_idx = 0
        self._vehicle_t = 0.0
        # Create vehicle dot
        x, y = self._vehicle_path_coords[0]
        r = T.VEHICLE_RADIUS
        self._vehicle_id = self.create_oval(
            x - r, y - r, x + r, y + r,
            fill=T.ROAD_ROUTE,
            outline=T.TEXT_PRIMARY,
            width=2,
            tags="vehicle",
        )
        self.tag_raise("vehicle")
        self._step_vehicle()

    def _step_vehicle(self) -> None:
        """Advance the vehicle dot one step along the route."""
        if self._vehicle_id is None:
            return
        coords = self._vehicle_path_coords
        if self._vehicle_seg_idx >= len(coords) - 1:
            # Reached end — pause then restart
            self.after(1500, self.animate_vehicle)
            return

        x1, y1 = coords[self._vehicle_seg_idx]
        x2, y2 = coords[self._vehicle_seg_idx + 1]
        self._vehicle_t += 0.04
        if self._vehicle_t >= 1.0:
            self._vehicle_t = 0.0
            self._vehicle_seg_idx += 1
            if self._vehicle_seg_idx >= len(coords) - 1:
                self.after(1500, self.animate_vehicle)
                return

        t = self._vehicle_t
        x = x1 + (x2 - x1) * t
        y = y1 + (y2 - y1) * t
        r = T.VEHICLE_RADIUS
        self.coords(self._vehicle_id, x - r, y - r, x + r, y + r)
        self.tag_raise("vehicle")
        self._anim_after_id = self.after(T.ANIM_VEHICLE_MS, self._step_vehicle)

    def _stop_vehicle(self) -> None:
        """Stop and remove the vehicle dot."""
        if self._anim_after_id:
            try:
                self.after_cancel(self._anim_after_id)
            except Exception:
                pass
            self._anim_after_id = None
        if self._vehicle_id is not None:
            try:
                self.delete(self._vehicle_id)
            except Exception:
                pass
            self._vehicle_id = None

    # ── Legend ────────────────────────────────────────────────────────────

    def _draw_legend(self) -> None:
        """Draw color-coded road legend at the bottom of the canvas."""
        cw = self.winfo_width()
        ch = self.winfo_height()
        y = ch - 30
        items = [
            (T.ROAD_NORMAL,  "Normal"),
            (T.ROAD_HAZARD2, "Hazard 2×"),
            (T.ROAD_HAZARD3, "Hazard 3×"),
            (T.ROAD_BLOCKED, "Blocked"),
            (T.ROAD_ROUTE,   "Route"),
            (T.NODE_SHELTER_BRD, "Shelter"),
            (T.NODE_START_BRD,   "Start"),
        ]
        x = 20
        for color, label in items:
            # Color swatch
            self.create_rectangle(x, y - 6, x + 20, y + 6,
                                  fill=color, outline="", tags="legend")
            x += 26
            self.create_text(x, y, text=label, fill=T.TEXT_MUTED,
                             font=T.FONT_LEGEND, anchor="w", tags="legend")
            x += len(label) * 6 + 16

    # ── Public API ────────────────────────────────────────────────────────

    def set_start_node(self, node_id: str) -> None:
        """Set the evacuation start node and redraw."""
        self._start_node = node_id
        self._full_redraw()

    def set_route(self, path: List[str]) -> None:
        """Set the active evacuation route path and redraw + animate."""
        self._stop_vehicle()
        self._route_path = path
        self._full_redraw()
        if path:
            self.after(200, self.animate_vehicle)

    def set_compare_path(self, path: List[str], show: bool) -> None:
        """Set the baseline comparison path."""
        self._compare_path = path
        self._show_compare = show
        self._full_redraw()

    def toggle_compare(self, show: bool) -> None:
        """Show or hide the comparison baseline path."""
        self._show_compare = show
        self._full_redraw()

    def refresh_edge(self, edge_id: str) -> None:
        """Refresh a single edge's visuals after state change."""
        self._redraw_edge(edge_id)

    def clear_route(self) -> None:
        """Remove the active route and vehicle."""
        self._stop_vehicle()
        self._route_path = []
        self._full_redraw()

    # ── Event Handlers ────────────────────────────────────────────────────

    def _node_left_click(self, node_id: str, event: tk.Event) -> None:
        self._start_node = node_id
        self._full_redraw()
        if self.on_start_changed:
            self.on_start_changed(node_id)

    def _edge_left_click(self, edge_id: str, event: tk.Event) -> None:
        if self.on_edge_blocked:
            self.on_edge_blocked(edge_id)

    def _edge_right_click(self, edge_id: str, event: tk.Event) -> None:
        if self.on_edge_hazard:
            self.on_edge_hazard(edge_id)

    def _on_left_click(self, event: tk.Event) -> None:
        """Handle background canvas click (no item hit)."""
        # No-op; node/edge clicks are handled via tag_bind
        pass

    def _on_right_click(self, event: tk.Event) -> None:
        """Handle background canvas right-click."""
        pass

    def _on_motion(self, event: tk.Event) -> None:
        """Hide tooltip on general motion (tooltip shows via tag_bind <Enter>)."""
        # Tooltip hide on motion away is handled by <Leave> bindings
        pass

    def _node_hover_enter(self, node_id: str, event: tk.Event) -> None:
        info = self._graph.get_node(node_id)
        if info is None:
            return
        ntype = "🏥 SHELTER" if info.is_shelter else "🔹 Intersection"
        if node_id == self._start_node:
            ntype = "🚨 START NODE"
        tip = f"{info.label}\nType: {ntype}\nID: {node_id}"
        x = event.x_root
        y = event.y_root
        self._tooltip.show(tip, x, y)

    def _edge_hover_enter(self, edge_id: str, event: tk.Event) -> None:
        pair = self._graph.get_edge_pair(edge_id)
        if pair is None:
            return
        fwd = pair[0]
        ef = fwd.effective_weight()
        ef_str = "∞ (BLOCKED)" if math.isinf(ef) else f"{ef:.1f} min"
        mul_str = "BLOCKED" if fwd.blocked else f"{fwd.hazard_multiplier:.1f}×"
        tip = (
            f"Road: {edge_id}\n"
            f"Route: {fwd.from_node} ↔ {fwd.to_node}\n"
            f"Base weight: {fwd.base_weight:.0f} min\n"
            f"Hazard: {mul_str}\n"
            f"Effective cost: {ef_str}\n"
            f"\n[Left-click]: Toggle blocked\n[Right-click]: Cycle hazard"
        )
        self._tooltip.show(tip, event.x_root, event.y_root)


# ─────────────────────────────────────────────────────────────────────────────
# ANALYTICS CARD
# ─────────────────────────────────────────────────────────────────────────────

class AnalyticsCard(tk.Frame):
    """A single statistic card in the analytics panel."""

    def __init__(
        self,
        parent: tk.Widget,
        label: str,
        initial: str = "—",
        unit: str = "",
        color: str = T.TEXT_PRIMARY,
        **kwargs,
    ) -> None:
        super().__init__(parent, bg=T.BG_CARD, **kwargs)
        self.config(relief="flat")
        # Inner border effect
        inner = tk.Frame(self, bg=T.BG_CARD, padx=T.PAD_MD, pady=T.PAD_MD)
        inner.pack(fill="both", expand=True)
        self._label_widget = tk.Label(
            inner, text=label, bg=T.BG_CARD,
            fg=T.TEXT_MUTED, font=T.FONT_CARD_LBL,
        )
        self._label_widget.pack(anchor="w")
        self._value_label = tk.Label(
            inner, text=initial, bg=T.BG_CARD,
            fg=color, font=T.FONT_CARD_VAL,
        )
        self._value_label.pack(anchor="w")
        self._unit = unit
        self._color = color

    def update(self, value: str, color: Optional[str] = None) -> None:
        """Update the displayed value."""
        self._value_label.config(text=value)
        if color:
            self._value_label.config(fg=color)


class PathCard(tk.Frame):
    """Analytics card for the path sequence (wraps across lines)."""

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        super().__init__(parent, bg=T.BG_CARD, **kwargs)
        inner = tk.Frame(self, bg=T.BG_CARD, padx=T.PAD_MD, pady=T.PAD_MD)
        inner.pack(fill="both", expand=True)
        tk.Label(
            inner, text="Path", bg=T.BG_CARD,
            fg=T.TEXT_MUTED, font=T.FONT_CARD_LBL,
        ).pack(anchor="w")
        self._val = tk.Label(
            inner, text="—", bg=T.BG_CARD,
            fg=T.ACCENT_BLUE, font=T.FONT_CODE_SM,
            wraplength=220, justify="left",
        )
        self._val.pack(anchor="w")

    def update(self, path_str: str) -> None:
        self._val.config(text=path_str)


# ─────────────────────────────────────────────────────────────────────────────
# HISTORY LOG WIDGET
# ─────────────────────────────────────────────────────────────────────────────

class HistoryLog(tk.Frame):
    """Scrollable path history log with timestamps."""

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        super().__init__(parent, bg=T.BG_PANEL, **kwargs)
        self._entries: List[str] = []

        header = tk.Frame(self, bg=T.BG_PANEL)
        header.pack(fill="x", padx=T.PAD_MD, pady=(T.PAD_MD, 0))
        tk.Label(
            header, text="Path History", bg=T.BG_PANEL,
            fg=T.TEXT_PRIMARY, font=T.FONT_BODY,
        ).pack(side="left")
        tk.Button(
            header, text="Clear", bg=T.BG_CARD, fg=T.TEXT_MUTED,
            font=T.FONT_BTN_SM, relief="flat", bd=0,
            activebackground=T.BG_CARD2, activeforeground=T.TEXT_PRIMARY,
            command=self._clear,
        ).pack(side="right")

        frame = tk.Frame(self, bg=T.BG_PANEL)
        frame.pack(fill="both", expand=True, padx=T.PAD_MD, pady=T.PAD_SM)

        self._text = tk.Text(
            frame, bg=T.BG_CARD, fg=T.TEXT_PRIMARY,
            font=T.FONT_LOG, relief="flat", bd=0,
            state="disabled", wrap="word",
            selectbackground=T.ACCENT_BLUE,
        )
        scrollbar = tk.Scrollbar(frame, command=self._text.yview,
                                  bg=T.BG_PANEL, troughcolor=T.BG_CARD)
        self._text.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._text.pack(side="left", fill="both", expand=True)

        # Tag styles
        self._text.tag_configure("timestamp", foreground=T.TEXT_DIM)
        self._text.tag_configure("route_ok",  foreground=T.ACCENT_BLUE)
        self._text.tag_configure("route_no",  foreground=T.DANGER)
        self._text.tag_configure("separator", foreground=T.BG_CARD2)

    def add_entry(self, result: RouteResult, start: str) -> None:
        """Prepend a new routing result to the log."""
        ts = datetime.now().strftime("%H:%M:%S")
        if result.reachable:
            dest = result.destination or "?"
            path_str = " → ".join(result.path)
            line1 = f"[{ts}]  {start} → {dest}"
            line2 = f"  Cost: {result.total_cost:.1f} min  |  Visited: {result.nodes_visited}  |  {result.exec_time_ms:.2f} ms"
            line3 = f"  {path_str}"
            entry = f"{line1}\n{line2}\n{line3}\n"
            tag = "route_ok"
        else:
            line1 = f"[{ts}]  {start} → NO ROUTE"
            entry = f"{line1}\n  All shelters unreachable.\n"
            tag = "route_no"

        self._entries.insert(0, entry)
        self._text.config(state="normal")
        self._text.insert("1.0", "─" * 35 + "\n", "separator")
        self._text.insert("1.0", entry, tag)
        self._text.config(state="disabled")

    def get_all_entries(self) -> List[str]:
        """Return all log entries as strings."""
        return list(self._entries)

    def _clear(self) -> None:
        self._entries.clear()
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        self._text.config(state="disabled")


# ─────────────────────────────────────────────────────────────────────────────
# STATUS CHIP
# ─────────────────────────────────────────────────────────────────────────────

class StatusChip(tk.Label):
    """Small colored pill showing system state."""

    _STATES = {
        "READY":    T.CHIP_READY,
        "ACTIVE":   T.CHIP_ACTIVE,
        "REROUTE":  T.CHIP_REROUTE,
        "NOROUTE":  T.CHIP_NOROUTE,
    }

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        super().__init__(
            parent,
            text="● SYSTEM READY",
            font=T.FONT_CHIP,
            padx=10, pady=4,
            relief="flat",
            **kwargs,
        )
        self._set("READY")

    def set_state(self, state: str) -> None:
        """State: 'READY' | 'ACTIVE' | 'REROUTE' | 'NOROUTE'."""
        self._set(state)

    def _set(self, state: str) -> None:
        fg, bg = self._STATES.get(state, T.CHIP_READY)
        labels = {
            "READY":   "● SYSTEM READY",
            "ACTIVE":  "● ROUTE ACTIVE",
            "REROUTE": "⟳ REROUTING",
            "NOROUTE": "✕ NO ROUTE",
        }
        self.config(text=labels.get(state, state), fg=fg, bg=bg)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APPLICATION
# ─────────────────────────────────────────────────────────────────────────────

class EvacuationApp:
    """
    Main application controller and view.

    Layout:
      ┌─────────────────────────────────────────────┐
      │  HEADER BAR (title, city, status chip)       │
      ├──────────────────────┬──────────────────────┤
      │  MAP CANVAS (left    │  SIDEBAR (right ~30%) │
      │  ~70%)               │  ├ Controls section   │
      │                      │  ├ Analytics cards    │
      │                      │  └ History log        │
      ├──────────────────────┴──────────────────────┤
      │  STATUS BAR                                  │
      └─────────────────────────────────────────────┘
    """

    _MAP_JSON = Path(__file__).parent / "map_data.json"

    def __init__(self) -> None:
        # ── Load graph ────────────────────────────────────────────────────
        try:
            self._graph = load_graph_from_json(self._MAP_JSON)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            # Friendly startup error
            root = tk.Tk()
            root.withdraw()
            mb.showerror("Startup Error", str(exc))
            root.destroy()
            return

        self._start_node: Optional[str] = None
        self._current_result: Optional[RouteResult] = None
        self._compare_mode: bool = False

        # ── Build window ──────────────────────────────────────────────────
        if CTK_AVAILABLE:
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")
            self._root = ctk.CTk()
        else:
            self._root = tk.Tk()

        self._root.title("Urban Disaster Evacuation & Smart Traffic Router")
        self._root.configure(bg=T.BG_DEEP)
        self._root.minsize(1100, 700)
        self._root.geometry("1300x800")

        self._build_ui()
        self._set_status("Click any node on the map to set the evacuation start point.")

    # ── UI Construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Construct the full dashboard layout."""
        root = self._root

        # ── Header bar ────────────────────────────────────────────────────
        header = _make_frame(root, bg=T.BG_PANEL)
        header.pack(fill="x", side="top")
        tk.Frame(header, bg=T.ACCENT_BLUE, width=4).pack(side="left", fill="y")

        title_frame = _make_frame(header, bg=T.BG_PANEL)
        title_frame.pack(side="left", padx=T.PAD_LG, pady=T.PAD_MD)
        tk.Label(
            title_frame,
            text="🚨  Urban Evacuation Router",
            bg=T.BG_PANEL, fg=T.TEXT_PRIMARY,
            font=T.FONT_TITLE,
        ).pack(anchor="w")
        tk.Label(
            title_frame,
            text=f"City: {self._graph.city_name}  •  V={self._graph.node_count} nodes  •  E={self._graph.edge_count} roads",
            bg=T.BG_PANEL, fg=T.TEXT_MUTED,
            font=T.FONT_SUBTITLE,
        ).pack(anchor="w")

        # Status chip (right side of header)
        self._chip = StatusChip(header, bg=T.CHIP_READY[1])
        self._chip.pack(side="right", padx=T.PAD_LG, pady=T.PAD_MD)

        # ── Main area ─────────────────────────────────────────────────────
        main = _make_frame(root, bg=T.BG_DEEP)
        main.pack(fill="both", expand=True)

        # Left: map canvas
        self._canvas = MapCanvas(main, self._graph, bg=T.MAP_BG)
        self._canvas.pack(side="left", fill="both", expand=True, padx=(T.PAD_MD, 0), pady=T.PAD_MD)
        self._canvas.on_start_changed = self._on_start_changed
        self._canvas.on_edge_blocked  = self._on_edge_blocked
        self._canvas.on_edge_hazard   = self._on_edge_hazard

        # Right: sidebar
        sidebar = _make_frame(main, bg=T.BG_PANEL, width=310)
        sidebar.pack(side="right", fill="y", padx=T.PAD_MD, pady=T.PAD_MD)
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        # ── Status bar ────────────────────────────────────────────────────
        self._status_bar = tk.Label(
            root, text="", bg=T.BG_PANEL, fg=T.TEXT_MUTED,
            font=T.FONT_STATUS, anchor="w", padx=T.PAD_MD, pady=4,
        )
        self._status_bar.pack(fill="x", side="bottom")

    def _build_sidebar(self, parent: tk.Frame) -> None:
        """Build the right sidebar: controls + analytics + history."""

        # ── No-route banner (hidden initially) ───────────────────────────
        self._no_route_banner = tk.Label(
            parent,
            text="⚠  No safe route available",
            bg=T.DANGER, fg=T.TEXT_PRIMARY,
            font=(T.FONT_FAMILY, 12, "bold"),
            pady=8,
        )
        # Not packed until needed

        # ── Controls ──────────────────────────────────────────────────────
        ctrl_frame = _make_frame(parent, bg=T.BG_PANEL)
        ctrl_frame.pack(fill="x", padx=T.PAD_MD, pady=(T.PAD_MD, 0))

        tk.Label(
            ctrl_frame, text="CONTROLS", bg=T.BG_PANEL,
            fg=T.TEXT_DIM, font=(T.FONT_FAMILY, 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))

        # Start node display
        start_row = _make_frame(ctrl_frame, bg=T.BG_CARD)
        start_row.pack(fill="x", pady=2)
        start_inner = _make_frame(start_row, bg=T.BG_CARD)
        start_inner.pack(fill="x", padx=T.PAD_MD, pady=8)
        tk.Label(
            start_inner, text="Start Node", bg=T.BG_CARD,
            fg=T.TEXT_MUTED, font=T.FONT_CARD_LBL,
        ).pack(anchor="w")
        self._start_label = tk.Label(
            start_inner, text="— Click a node to select —",
            bg=T.BG_CARD, fg=T.WARNING,
            font=(T.FONT_FAMILY, 12, "bold"),
        )
        self._start_label.pack(anchor="w")

        btn_style = dict(
            bg=T.ACCENT_BLUE, fg=T.TEXT_PRIMARY,
            font=T.FONT_BTN, relief="flat", bd=0,
            activebackground=T.ACCENT_BLUE2,
            activeforeground=T.TEXT_PRIMARY,
            cursor="hand2",
        )
        sm_btn_style = dict(
            bg=T.BG_CARD, fg=T.TEXT_PRIMARY,
            font=T.FONT_BTN_SM, relief="flat", bd=0,
            activebackground=T.BG_CARD2,
            activeforeground=T.TEXT_PRIMARY,
            cursor="hand2",
        )

        # Run Evacuation
        tk.Button(
            ctrl_frame, text="🚀  Run Evacuation",
            **btn_style, pady=10,
            command=self._run_evacuation,
        ).pack(fill="x", pady=(6, 2))

        # Reset All Hazards
        tk.Button(
            ctrl_frame, text="↺  Reset All Hazards",
            **sm_btn_style, pady=8,
            command=self._reset_hazards,
        ).pack(fill="x", pady=2)

        # Compare to Normal toggle
        self._compare_var = tk.BooleanVar(value=False)
        self._compare_btn = tk.Checkbutton(
            ctrl_frame, text="⟳  Compare to Normal Route",
            variable=self._compare_var,
            bg=T.BG_CARD, fg=T.TEXT_PRIMARY,
            font=T.FONT_BTN_SM,
            selectcolor=T.ACCENT_BLUE,
            activebackground=T.BG_CARD,
            activeforeground=T.TEXT_PRIMARY,
            relief="flat", bd=0,
            command=self._toggle_compare,
        )
        self._compare_btn.pack(fill="x", pady=2)

        # Export Log
        tk.Button(
            ctrl_frame, text="💾  Export Log",
            **sm_btn_style, pady=8,
            command=self._export_log,
        ).pack(fill="x", pady=2)

        # ── Separator ─────────────────────────────────────────────────────
        tk.Frame(parent, bg=T.BORDER, height=1).pack(fill="x", padx=T.PAD_MD, pady=T.PAD_MD)

        # ── Analytics cards ───────────────────────────────────────────────
        tk.Label(
            parent, text="ANALYTICS", bg=T.BG_PANEL,
            fg=T.TEXT_DIM, font=(T.FONT_FAMILY, 9, "bold"),
        ).pack(anchor="w", padx=T.PAD_LG)

        cards_frame = _make_frame(parent, bg=T.BG_PANEL)
        cards_frame.pack(fill="x", padx=T.PAD_MD, pady=T.PAD_SM)

        def card(lbl: str, init: str = "—", color: str = T.TEXT_PRIMARY) -> AnalyticsCard:
            c = AnalyticsCard(cards_frame, label=lbl, initial=init, color=color)
            c.pack(fill="x", pady=2)
            return c

        self._card_time      = card("Total Travel Time",   color=T.SUCCESS)
        self._card_visited   = card("Nodes Visited",       color=T.ACCENT_BLUE)
        self._card_exec      = card("Execution Time",      color=T.TEXT_MUTED)
        self._card_dest      = card("Destination Shelter", color=T.SUCCESS)
        self._path_card      = PathCard(cards_frame)
        self._path_card.pack(fill="x", pady=2)

        # ── Separator ─────────────────────────────────────────────────────
        tk.Frame(parent, bg=T.BORDER, height=1).pack(fill="x", padx=T.PAD_MD, pady=T.PAD_SM)

        # ── History log ───────────────────────────────────────────────────
        self._history = HistoryLog(parent)
        self._history.pack(fill="both", expand=True)

    # ── Event Handlers ────────────────────────────────────────────────────

    def _on_start_changed(self, node_id: str) -> None:
        """Called when the user clicks a node to set start."""
        self._start_node = node_id
        info = self._graph.get_node(node_id)
        label = info.label if info else node_id
        self._start_label.config(text=f"  {node_id}  —  {label.split('/')[0]}")
        self._set_status(f"Start node set to {node_id}. Click 'Run Evacuation' or modify roads.")
        self._run_evacuation()   # Instant re-route

    def _on_edge_blocked(self, edge_id: str) -> None:
        """Called when left-clicking an edge to toggle blocked."""
        self._graph.toggle_edge_blocked(edge_id)
        self._canvas.refresh_edge(edge_id)
        pair = self._graph.get_edge_pair(edge_id)
        state = "BLOCKED" if (pair and pair[0].blocked) else "OPEN"
        self._set_status(f"Road {edge_id}: {state}  •  Route updated instantly.")
        self._run_evacuation()

    def _on_edge_hazard(self, edge_id: str) -> None:
        """Called when right-clicking an edge to cycle hazard."""
        self._graph.cycle_edge_hazard(edge_id)
        self._canvas.refresh_edge(edge_id)
        pair = self._graph.get_edge_pair(edge_id)
        if pair:
            mul = pair[0].hazard_multiplier
            self._set_status(f"Road {edge_id}: hazard now {mul:.0f}×  •  Route updated instantly.")
        self._run_evacuation()

    def _run_evacuation(self) -> None:
        """Compute shortest path and update all UI elements."""
        if not self._start_node:
            self._set_status("Please click a node on the map to set the start point.")
            return

        self._chip.set_state("REROUTE")
        self._root.update_idletasks()

        # Run Dijkstra
        result = self._graph.dijkstra(self._start_node)
        self._current_result = result

        if result.reachable:
            self._chip.set_state("ACTIVE")
            self._no_route_banner.pack_forget()
            self._canvas.set_route(result.path)

            dest_info = self._graph.get_node(result.destination or "")
            dest_label = dest_info.label if dest_info else (result.destination or "?")

            self._card_time.update(f"{result.total_cost:.1f} min", T.SUCCESS)
            self._card_visited.update(str(result.nodes_visited), T.ACCENT_BLUE)
            self._card_exec.update(f"{result.exec_time_ms:.3f} ms")
            self._card_dest.update(result.destination or "?", T.SUCCESS)
            path_str = " → ".join(result.path)
            self._path_card.update(path_str)
        else:
            self._chip.set_state("NOROUTE")
            self._no_route_banner.pack(fill="x", padx=T.PAD_MD, pady=T.PAD_SM, before=self._history)
            self._canvas.clear_route()
            self._card_time.update("∞", T.DANGER)
            self._card_visited.update(str(result.nodes_visited), T.TEXT_MUTED)
            self._card_exec.update(f"{result.exec_time_ms:.3f} ms")
            self._card_dest.update("None", T.DANGER)
            self._path_card.update("No route available")

        # Update compare overlay
        if self._compare_mode:
            comp = self._graph.dijkstra_no_hazard(self._start_node)
            self._canvas.set_compare_path(comp.path, True)

        # Log entry
        self._history.add_entry(result, self._start_node)

    def _reset_hazards(self) -> None:
        """Reset all hazards and re-route."""
        self._graph.reset_all_edges()
        self._set_status("All hazards reset. Roads restored to normal.")
        # Refresh all edge visuals
        for eid in self._graph.get_all_edge_pairs():
            self._canvas.refresh_edge(eid)
        self._run_evacuation()

    def _toggle_compare(self) -> None:
        """Toggle the no-hazard comparison overlay."""
        self._compare_mode = self._compare_var.get()
        if self._compare_mode and self._start_node:
            comp = self._graph.dijkstra_no_hazard(self._start_node)
            self._canvas.set_compare_path(comp.path, True)
        else:
            self._canvas.toggle_compare(False)

    def _export_log(self) -> None:
        """Save the path history log to a .txt file."""
        entries = self._history.get_all_entries()
        if not entries:
            mb.showinfo("Export Log", "No history entries to export.")
            return
        filepath = fd.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="Export Evacuation Log",
        )
        if not filepath:
            return
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"Evacuation Router — {self._graph.city_name}\n")
                f.write(f"Exported: {datetime.now().isoformat()}\n")
                f.write("=" * 60 + "\n\n")
                for entry in entries:
                    f.write(entry + "\n")
            mb.showinfo("Export Log", f"Log saved to:\n{filepath}")
        except OSError as exc:
            mb.showerror("Export Error", str(exc))

    def _set_status(self, msg: str) -> None:
        """Update the bottom status bar text."""
        self._status_bar.config(text=f"  ℹ  {msg}")

    # ── Run ───────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the Tkinter event loop."""
        self._root.mainloop()
