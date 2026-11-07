"""Map scale / grid model: world/<place>/view_settings.json + CLI overrides.

  cfg = viewcfg.load(place, preset="town", scale=None, grid=None, page=None)
  cfg -> dict: preset, scale_ft_per_in, grid_ft, grid_major_every, page_in, margin_in, focus, scale_bar_ft,
               units, min_street_width_ft, contour_mask, label_offset
  grid_extent = "window" (default, the grid stays inside the place bounds so margins are clean paper) | "page" (full page)
  label_offset = {enabled, style: straight|elbow, stroke_width (pt), margin_pct, max_offset_pt (page pt), dot}; see label_offset.py
Scale bar length defaults to 5 paper inches of ground. Feet are always the model unit; only drawing changes.
"""
import json
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
FALLBACK = {
    "units": "ft", "page_in": [17, 11], "margin_in": 0.5, "min_street_width_ft": 10, "default_preset": "town",
    "contour_mask": {"enabled": True, "include": ["buildings", "streets", "plazas"]},
    "label_offset": {"enabled": True, "style": "elbow", "stroke_width": 0.4, "margin_pct": 10, "max_offset_pt": 90, "dot": True},
    "presets": {
        "town": {"scale_ft_per_in": 100, "grid_ft": 100, "grid_major_every": 5, "focus": [1200, 750]},
        "bowl": {"scale_ft_per_in": 200, "grid_ft": 100, "grid_major_every": 5, "focus": "center"},
        "street": {"scale_ft_per_in": 20, "grid_ft": 20, "grid_major_every": 5, "focus": "entity"},
        "room": {"scale_ft_per_in": 5, "grid_ft": 5, "grid_major_every": 5, "focus": "entity"},
    },
}
VIEW_TO_PRESET = {"town": "town", "bowl": "bowl", "street": "street", "building": "room", "room": "room"}


def load_raw(place):
    p = os.path.join(REPO, "world", place, "view_settings.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return FALLBACK


def label_offset(place):
    """Label-offset settings (leader lines) from view_settings.json, falling back to the defaults."""
    return {**FALLBACK["label_offset"], **load_raw(place).get("label_offset", {})}


def label_style(place):
    """label_style block of view_settings.json (fonts, wrapping, halo/box/mask; see label_style.py), {} when absent."""
    return load_raw(place).get("label_style", {})


def parse_page(s):
    if s is None:
        return None
    if isinstance(s, (list, tuple)):
        return [float(s[0]), float(s[1])]
    a, b = str(s).lower().replace(",", "x").split("x")
    return [float(a), float(b)]


def load(place, preset="town", scale=None, grid=None, page=None, major_every=None, grid_extent=None):
    raw = load_raw(place)
    preset = VIEW_TO_PRESET.get(preset, preset)
    presets = raw.get("presets", FALLBACK["presets"])
    if preset not in presets:
        raise SystemExit(f"unknown preset {preset!r}; have {sorted(presets)}")
    c = {k: v for k, v in raw.items() if k != "presets"}
    c.update(presets[preset])
    c["preset"] = preset
    if scale:
        c["scale_ft_per_in"] = float(scale)
        c.pop("scale_bar_ft", None)
    if grid:
        c["grid_ft"] = float(grid)
    if major_every:
        c["grid_major_every"] = int(major_every)
    c["page_in"] = parse_page(page) or c.get("page_in", [17, 11])
    c.setdefault("grid_major_every", 5)
    c.setdefault("margin_in", 0.5)
    if not c.get("scale_bar_ft"):
        c["scale_bar_ft"] = _nice(5 * c["scale_ft_per_in"])
    return c
    if grid_extent:
        c["grid_extent"] = grid_extent            # "window" (default: grid only inside the map window) | "page" (whole page)


def _nice(v):
    import math
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * e * 1.0001:
            return m * e
    return v
