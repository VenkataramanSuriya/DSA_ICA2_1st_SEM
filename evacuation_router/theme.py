"""
theme.py — Centralized color palette, fonts, and spacing constants.

All visual styling tokens for the Evacuation Router dashboard.
No widget code here — purely constants.
"""

# ─── Color Palette ───────────────────────────────────────────────────────────
BG_DEEP      = "#0f1117"   # Window / root background
BG_PANEL     = "#1a1d27"   # Sidebar / panel background
BG_CARD      = "#232736"   # Analytics cards
BG_CARD2     = "#1e2130"   # Secondary card variant
BG_INPUT     = "#2a2d3e"   # Entry / combobox fill

TEXT_PRIMARY = "#e8eaed"   # Main text
TEXT_MUTED   = "#9aa0a6"   # Secondary / hint text
TEXT_DIM     = "#5f6368"   # Disabled / very dim text

ACCENT_BLUE  = "#4c8dff"   # Primary accent (buttons, selected items)
ACCENT_BLUE2 = "#3a7de8"   # Darker blue for hover states
SUCCESS      = "#34a853"   # Safe / shelter / "ROUTE ACTIVE"
WARNING      = "#f4b400"   # Hazard 2× / "REROUTING"
DANGER       = "#ea4335"   # Blocked / error / "NO ROUTE"
ORANGE       = "#ff6d00"   # Hazard 3×
BORDER       = "#2d3148"   # Card/panel borders

# ─── Map Canvas Colors ────────────────────────────────────────────────────────
MAP_BG           = "#12141e"   # Canvas background
MAP_GRID         = "#1c1f2e"   # Subtle grid lines
ROAD_NORMAL      = "#4a4e6a"   # Normal road
ROAD_HAZARD2     = "#f4b400"   # 2× hazard road (yellow)
ROAD_HAZARD3     = "#ff6d00"   # 3× hazard road (orange)
ROAD_BLOCKED     = "#ea4335"   # Blocked road (red)
ROAD_ROUTE       = "#00d4ff"   # Active evacuation route (cyan)
ROAD_ROUTE_GLOW  = "#004c6e"   # Glow underlay for route (thick translucent)
ROAD_COMPARE     = "#4c8dff"   # Comparison (no-hazard) route (faint blue)

NODE_NORMAL      = "#2a3050"   # Normal intersection node fill
NODE_NORMAL_BG   = "#1a1d27"
NODE_BORDER      = "#4a4e6a"   # Node border
NODE_SHELTER     = "#1a4a2e"   # Shelter fill (dark green)
NODE_SHELTER_BRD = "#34a853"   # Shelter border (bright green)
NODE_START       = "#5a3e00"   # Start node fill (amber dark)
NODE_START_BRD   = "#f4b400"   # Start node border (amber)
NODE_ROUTE_HL    = "#00d4ff"   # Route node highlight border
NODE_TEXT        = "#e8eaed"   # Node label text

# ─── Chip / Status Colors ─────────────────────────────────────────────────────
CHIP_READY    = ("#34a853", "#1a4a2e")   # (fg, bg)
CHIP_ACTIVE   = ("#00d4ff", "#003a4a")
CHIP_REROUTE  = ("#f4b400", "#3d2e00")
CHIP_NOROUTE  = ("#ea4335", "#3a0d09")

# ─── Typography ──────────────────────────────────────────────────────────────
FONT_FAMILY   = "Segoe UI"
FONT_FALLBACK = ("Segoe UI", "Helvetica Neue", "Helvetica", "Arial")

FONT_TITLE    = (FONT_FAMILY, 20, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 12)
FONT_CARD_LBL = (FONT_FAMILY, 10)
FONT_CARD_VAL = (FONT_FAMILY, 22, "bold")
FONT_CARD_VAL_SM = (FONT_FAMILY, 14, "bold")
FONT_BODY     = (FONT_FAMILY, 12)
FONT_BODY_SM  = (FONT_FAMILY, 11)
FONT_CODE     = ("Consolas", 11)
FONT_CODE_SM  = ("Consolas", 10)
FONT_BTN      = (FONT_FAMILY, 12, "bold")
FONT_BTN_SM   = (FONT_FAMILY, 11)
FONT_CHIP     = (FONT_FAMILY, 10, "bold")
FONT_STATUS   = (FONT_FAMILY, 11)
FONT_LEGEND   = (FONT_FAMILY, 10)
FONT_TOOLTIP  = (FONT_FAMILY, 10)
FONT_LOG      = ("Consolas", 10)
FONT_NODE_LABEL = ("Segoe UI", 8, "bold")
FONT_HEADER_NODE = (FONT_FAMILY, 9)

# ─── Spacing & Geometry ───────────────────────────────────────────────────────
PAD_SM   = 6
PAD_MD   = 12
PAD_LG   = 16
PAD_XL   = 24
RADIUS   = 8    # Corner radius for cards
RADIUS_LG = 12

# ─── Road Widths ─────────────────────────────────────────────────────────────
ROAD_WIDTH_NORMAL  = 3
ROAD_WIDTH_HAZARD  = 4
ROAD_WIDTH_BLOCKED = 3
ROAD_WIDTH_ROUTE   = 5
ROAD_WIDTH_GLOW    = 12   # Glow underlay width

# ─── Node Sizes ───────────────────────────────────────────────────────────────
NODE_RADIUS        = 18
NODE_SHELTER_EXTRA = 4    # Shelter nodes are slightly larger
NODE_HIT_RADIUS    = 20   # Click hit area

# ─── Animation ────────────────────────────────────────────────────────────────
ANIM_FADE_MS   = 200   # Color transition duration (ms)
ANIM_STEPS     = 10    # Steps for color interpolation
ANIM_VEHICLE_MS = 30   # Vehicle dot step interval (ms)
VEHICLE_RADIUS  = 7    # Traveling dot radius
