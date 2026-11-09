"""Home interior style presets (presets/interiors/presets.json, also read by the plugin panel lib/core.js, which has a test that its list matches).

Selection order for a building: building JSON / entity key `interior_style` (per building) > pack manifest foundry.interior_style (per scene, set by
`worldpack.py export|split|reexport --interior-style`) > kind_map by building kind ("auto", the default). Unknown names fall back to "auto".
`plain` is the original look and the style of every kind that kind_map does not list (inns, shops, barns, civic buildings ...).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PRESET_FILE = os.path.join(HERE, "..", "presets", "interiors", "presets.json")
_CACHE = {}


def table():
    if "t" not in _CACHE:
        with open(PRESET_FILE, encoding="utf-8") as f:
            _CACHE["t"] = json.load(f)
    return _CACHE["t"]


def names():
    return list(table()["styles"])


def choices():
    """Valid values of the scene / building setting: 'auto' + every style."""
    return ["auto"] + names()


def check(name, allow_none=True):
    """-> a valid setting string; unknown / empty -> 'auto'."""
    s = str(name or "").strip().lower()
    return s if s in choices() else "auto"


def style_for_kind(kind):
    t = table()
    k = str(kind or "default").lower()
    return t["kind_map"].get(k, "plain" if k not in ("default",) else t["kind_map"].get("default", "plain"))


def resolve_name(building, scene_style=None):
    """Style name for a building entity / dict (keys: interior_style, kind)."""
    b = check((building or {}).get("interior_style"))
    if b != "auto":
        return b
    s = check(scene_style)
    if s != "auto":
        return s
    return style_for_kind((building or {}).get("kind"))


def get(name):
    """Preset dict (a copy with 'name' added); unknown -> plain."""
    t = table()["styles"]
    if name not in t:
        name = "plain"
    return dict(t[name], name=name)


def scene_style(pack):
    """The per-scene setting recorded in a pack manifest ('auto' when absent)."""
    try:
        return check(pack.manifest.get("foundry", {}).get("interior_style"))
    except AttributeError:
        return "auto"
