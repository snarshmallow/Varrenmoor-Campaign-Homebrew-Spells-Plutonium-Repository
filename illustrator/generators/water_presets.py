"""3D water presets and per-place settings (river / pond / lake / ocean).

Source of truth: presets/water/presets.json (also read by the plugin panel, panel/lib/water.js, which has a test that its table matches).
Per-place settings live in the panel state (world/<place>/panel_state.json, key "water3d", READ ONLY here):
  {"preset": "river", "force": false, "values": {"river": {"flow_speed": 2.0, ...}, "lake": {...}}}
Each water entity uses the preset of its own kind (kind_map) unless `force` is on (then every water body uses `preset`), with the saved values of that preset on
top of the preset defaults. resolve() clamps every number to the declared range, so a hand-edited file cannot feed the shader nonsense.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PRESET_FILE = os.path.join(HERE, "..", "presets", "water", "presets.json")
_CACHE = {}


def table():
    if "t" not in _CACHE:
        with open(PRESET_FILE, encoding="utf-8") as f:
            _CACHE["t"] = json.load(f)
    return _CACHE["t"]


def preset_names():
    return list(table()["presets"])


def preset_for_kind(kind):
    t = table()
    return t["kind_map"].get(str(kind or "").lower(), t["default_preset"])


def _num(v, lo, hi, d):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return d
    if v != v:
        return d
    return max(lo, min(hi, v))


def _color(v, d):
    s = str(v or "")
    if len(s) == 7 and s[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in s[1:]):
        return s.lower()
    return d


def resolve(preset, values=None):
    """Full parameter dict for a preset: defaults + saved overrides, clamped. Unknown preset -> default preset."""
    t = table()
    if preset not in t["presets"]:
        preset = t["default_preset"]
    base = t["presets"][preset]
    out = {"preset": preset, "mode": base["mode"]}
    for k, spec in t["params"].items():
        out[k] = _num((values or {}).get(k, base[k]), spec["min"], spec["max"], base[k])
    out["slope_speed"] = _num((values or {}).get("slope_speed", base["slope_speed"]), 0.0, 1.0, base["slope_speed"])
    out["shallow_color"] = _color((values or {}).get("shallow_color"), base["shallow_color"])
    out["deep_color"] = _color((values or {}).get("deep_color"), base["deep_color"])
    return out


def load_place_settings(place, world_root=None):
    """The panel's saved water3d block for a place ({} when there is none). Read only."""
    root = world_root or os.path.join(REPO, "world")
    try:
        with open(os.path.join(root, place, "panel_state.json"), encoding="utf-8") as f:
            return (json.load(f) or {}).get("water3d") or {}
    except (OSError, ValueError):
        return {}


def settings_for(kind, settings=None):
    """Resolved parameters for a water entity of this kind under the place settings (None = defaults)."""
    s = settings or {}
    pre = s.get("preset") if s.get("force") and s.get("preset") in table()["presets"] else preset_for_kind(kind)
    return resolve(pre, (s.get("values") or {}).get(pre))


def material_name(preset):
    return f"VB_water_{preset}"


def preset_of_material(name):
    n = str(name or "")
    return n[len("VB_water_"):] if n.startswith("VB_water_") else None
