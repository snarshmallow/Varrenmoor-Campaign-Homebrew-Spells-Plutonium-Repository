"""Terrain statistics and elevation remapping so the shipped elevation-banded presets work on any place.

The terrain phase presets (presets/terrain_phases/*.json), skybox snow / tree lines and similar were tuned against the Bridgehollow
heightmap (2nd to 98th percentile elevation 625..1002 ft above sea level). A place of another shape (a sea-level fishing village,
a 3000 ft pass) would put every pixel in one band. With place.json `"phase_elevation": "percentile"` the absolute thresholds are
mapped linearly from that reference range onto the place's own p02..p98 range; thresholds within SHORE_FT of the datum stay
sea-level-relative (shore / beach bands). Places without the key (Bridgehollow) keep the absolute thresholds, so their output
does not change.

  place_stats.adapt_info(h, sea_ft)         -> {"lo", "hi", "sea"}  (hi is at least lo + MIN_RANGE_FT)
  place_stats.remap(v, info)                -> mapped threshold (None passes through)
  place_stats.adapt_phases(phases, info)    -> new phase list (elev_min / elev_max / elev_blend_ft rescaled)
  place_stats.place_adapt(place, h, sea)    -> info when place.json asks for it, else None
"""
import copy
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
REF_LO, REF_HI = 625.0, 1002.0      # Bridgehollow p02 / p98, the range the presets were tuned on
SHORE_FT = 40.0                     # |threshold - sea| below this: stays relative to the datum
MIN_RANGE_FT = 200.0                # flat places: pretend at least this much relief so lowland bands stay lowland


def adapt_info(h, sea_ft=0.0):
    lo, hi = np.percentile(h, [2, 98])
    lo, hi = float(lo), float(hi)
    return {"lo": lo, "hi": max(hi, lo + MIN_RANGE_FT), "sea": float(sea_ft)}


def remap(v, info):
    if v is None or info is None:
        return v
    v = float(v)
    if abs(v - info["sea"]) <= SHORE_FT:
        return v
    return info["lo"] + (v - REF_LO) / (REF_HI - REF_LO) * (info["hi"] - info["lo"])


def scale_of(info):
    return min(max((info["hi"] - info["lo"]) / (REF_HI - REF_LO), 0.25), 3.0)


def adapt_phases(phases, info):
    if not info:
        return phases
    out = copy.deepcopy(phases)
    k = scale_of(info)
    for p in out:
        for key in ("elev_min", "elev_max"):
            if p.get(key) is not None:
                p[key] = round(remap(p[key], info), 2)
        if p.get("elev_blend_ft") is not None:
            p["elev_blend_ft"] = round(float(p["elev_blend_ft"]) * k, 2)
    return out


def place_json(place, root=None):
    p = os.path.join(root or os.path.join(REPO, "world"), place, "place.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def place_adapt(place, h, sea_ft=0.0, root=None):
    if place_json(place, root).get("phase_elevation") == "percentile":
        return adapt_info(h, sea_ft)
    return None
