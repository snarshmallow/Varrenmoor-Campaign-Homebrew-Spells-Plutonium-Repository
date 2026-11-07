"""Label declutter: tiers + scale visibility, pinned positions (label_overrides.json), Label QA, numbered legend, presets.

  dc = label_declutter.merge(view_settings.get("declutter"), cli_declutter)      # config dict (see DEFAULT)
  tier = label_declutter.tier_of(kind, category)                                  # districts | plazas | civic | streets | houses | rooms
  label_declutter.visible(dc, tier, fpi)                                          # False = too small for this view scale -> hidden layer
  ov = label_declutter.load_overrides(place)                                      # {entity id: {x_ft, y_ft, anchor_ft?}}  (world/<place>/label_overrides.json)
  qa = label_declutter.qa_report(placer, rows)                                    # overlap / occlusion numbers, printed and written next to the svg
  label_declutter.legend_svg(entries, box, st)                                    # numbered key for labels set as numbered markers
  label_declutter.preset(name)                                                    # presets/label_presets.json: label_style + label_offset + declutter

CLI (used by the panel):
  python label_declutter.py pin   --place P --positions positions.json --manifest M.labels.json    # write moved labels into label_overrides.json
  python label_declutter.py clear --place P [--ids a,b]
  python label_declutter.py list  --place P
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PRESET_FILE = os.path.join(HERE, "..", "presets", "label_presets.json")

TIERS = ["districts", "plazas", "civic", "streets", "houses"]
TIER_LABEL = {"districts": "Districts", "plazas": "Plazas", "civic": "Civic and trade", "streets": "Streets", "houses": "Houses and farms", "rooms": "Rooms"}
LAYER_HIDDEN, LAYER_LEGEND, LAYER_MARKERS = "Labels - Hidden", "Legend", "Callout Markers"

DEFAULT = {
    "enabled": True,
    "scale_visibility": True,       # hide tiers whose max_fpi is below the view scale (ft per inch)
    "tiers": {
        "districts": {"priority": 1, "max_fpi": 1000, "size": 1.0, "number": False, "max_cover": None},
        "plazas": {"priority": 2, "max_fpi": 1000, "size": 1.0, "number": False, "max_cover": None},
        "civic": {"priority": 3, "max_fpi": 250, "size": 1.0, "number": False, "max_cover": 0.75},
        "streets": {"priority": 4, "max_fpi": 150, "size": 0.95, "number": False, "max_cover": 0.6},
        "houses": {"priority": 5, "max_fpi": 45, "size": 0.9, "number": False, "max_cover": 0.4, "leader": False},
    },
    "collision": "hide",            # a label that finds no free spot: hide (hidden sublayer) | number (marker + legend) | keep (overlap)
    "score": True,                  # place by how little of the map the text covers
    "weights": {"building": 1.0, "plaza": 0.45, "road": 1.0, "water": 4.0, "junction": 0.5},
    "area_move": 0.30,              # an area label that still covers this much (weighted) inside its shape is tried outside with a leader
    "legend": True,
    "legend_title": "Key",
    "overrides": True,              # honour world/<place>/label_overrides.json
    "curved_streets": False,        # street names along a curved baseline (textPath) where the street bends
    "min_curve_deg": 12.0,
    "qa": True,
    "quiet": False,                 # smaller text, thin dotted leaders
    "contrast_png": "",             # path of a shading PNG (+ .json sidecar); labels over dark terrain get light text with a dark halo
    "abbreviations": {},            # extra word -> abbreviation pairs (on top of presets/label_abbreviations.json)
}
LEGACY = {"enabled": False, "scale_visibility": False, "collision": "keep", "score": False, "legend": False, "overrides": False, "qa": True}


def merge(*layers):
    out = json.loads(json.dumps(DEFAULT))
    for lay in layers:
        for k, v in (lay or {}).items():
            if v is None:
                continue
            if k == "tiers":
                for t, d in (v or {}).items():
                    out["tiers"].setdefault(t, {}).update({a: b for a, b in (d or {}).items()})
            elif k in ("weights", "abbreviations"):
                out[k].update(v or {})
            else:
                out[k] = v
    if not out.get("enabled", True):
        for k, v in LEGACY.items():
            out[k] = v
        out["enabled"] = False
    return out


def parse_cli(text):
    if not text:
        return {}
    if text.startswith("@"):
        with open(text[1:], encoding="utf-8") as f:
            return json.load(f)
    return json.loads(text)


def tier_of(kind, category):
    """Tier name of a label from the entity kind / label category."""
    if category == "rooms":
        return "rooms"
    if category == "districts":
        return "plazas" if kind == "square" else "districts"
    if category == "streets":
        return "civic" if kind in ("road", "bridge") else "streets"
    if category == "buildings":
        return "houses" if kind in ("house", "shed", "farmhouse", "barn") else "civic"
    return "civic"


def tier_cfg(dc, tier):
    return dc["tiers"].get(tier) or {"priority": 3, "max_fpi": 1e9, "size": 1.0, "number": False, "max_cover": None}


def visible(dc, tier, fpi):
    if not dc.get("scale_visibility") or tier == "rooms":
        return True
    return fpi <= float(tier_cfg(dc, tier).get("max_fpi") or 1e9)


# ------------------------------------------------------------------ presets
def load_presets(path=None):
    try:
        with open(path or PRESET_FILE, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


def preset(name, path=None):
    p = load_presets(path).get(name)
    if p is None:
        raise SystemExit(f"unknown label preset {name!r}; have {sorted(load_presets(path))}")
    return p


# ------------------------------------------------------------------ overrides (pinned label positions, feet)
def overrides_path(place):
    return os.path.join(REPO, "world", place, "label_overrides.json")


def load_overrides(place):
    try:
        with open(overrides_path(place), encoding="utf-8") as f:
            return (json.load(f) or {}).get("labels", {})
    except (OSError, ValueError):
        return {}


def save_overrides(place, labels):
    p = overrides_path(place)
    doc = {"_note": "Label positions pinned from Illustrator (panel: Labels > Pin label positions). Feet in the world frame; the text block "
                    "centre x_ft/y_ft, and anchor_ft (where the leader points) when the anchor dot was moved. Keyed by entity id. "
                    "Regeneration places an overridden label exactly here and recomputes its leader.",
           "labels": labels}
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    return p


def pin_positions(place, positions, manifest, tol_pt=1.5, anchor_tol_pt=1.0):
    """positions: [{id (label id, '<entity>_label'), cx, cy (page pt, y down), ref: [x, y]|None (where the label was generated, from the
    item note / backing), anchor: [x, y]|None (current dot)}]; manifest: the .labels.json of the render (view mapping + generated
    positions). Labels moved more than tol_pt are written to label_overrides.json (feet). -> (n_pinned, n_anchor, moved ids)."""
    k, x0, y0, m = manifest["k"], manifest["x0"], manifest["y0"], manifest["margin_pt"]
    ft = lambda px, py: [round((px - m) / k + x0, 2), round((py - m) / k + y0, 2)]
    labels = load_overrides(place)
    moved, n_anchor = [], 0
    for p in positions:
        ent = p["id"][:-6] if p["id"].endswith("_label") else p["id"]
        gen = manifest.get("labels", {}).get(ent) or {}
        ref = p.get("ref") or ([gen["cx"], gen["cy"]] if gen else None)
        if ref is None:
            continue
        d = math.hypot(p["cx"] - ref[0], p["cy"] - ref[1])
        a_moved = bool(p.get("anchor") and gen.get("anchor") and math.hypot(p["anchor"][0] - gen["anchor"][0], p["anchor"][1] - gen["anchor"][1]) > anchor_tol_pt)
        if d <= tol_pt and not a_moved:
            continue
        rec = labels.get(ent, {})
        if d > tol_pt:
            x_, y_ = ft(p["cx"], p["cy"])
            rec.update({"x_ft": x_, "y_ft": y_})
        if a_moved:
            rec["anchor_ft"] = ft(*p["anchor"])
            n_anchor += 1
        if "x_ft" not in rec:                      # only the anchor moved: keep the generated label spot
            x_, y_ = ft(gen["cx"], gen["cy"])
            rec.update({"x_ft": x_, "y_ft": y_})
        labels[ent] = rec
        moved.append(ent)
    save_overrides(place, labels)
    return len(moved), n_anchor, moved


def clear_overrides(place, ids=None):
    labels = load_overrides(place)
    n = len(labels)
    if ids:
        for i in ids:
            labels.pop(i, None)
    else:
        labels = {}
    save_overrides(place, labels)
    return n - len(labels)


# ------------------------------------------------------------------ QA
def qa_report(placer, rows, contour_boxes=()):
    """rows: [{id, text, tier, status (placed|hidden|numbered), why (scale|collision|None), box (shapely, page pt), leader (pts|None), pinned}].
    -> dict with the numbers printed by render_world and written to <svg>.qa.json."""
    from shapely.geometry import LineString
    shown = [r for r in rows if r["status"] == "placed"]
    tot_a = cov_a = 0.0
    per, over = [], 0
    kinds = {}
    for r in shown:
        b = r["box"]
        cov = placer.cover(b, r["id"]) if placer._feat else {}
        frac = min(sum(f for k_, f in cov.items() if k_ != "junction"), 1.0)
        tot_a += b.area
        cov_a += b.area * frac
        for k_, f in cov.items():
            if k_ == "junction":
                continue
            kinds[k_] = kinds.get(k_, 0.0) + f * b.area
        if frac > 0.25:
            over += 1
        per.append((frac, r["id"], r["text"], r["tier"], {k_: round(f, 2) for k_, f in cov.items()}))
    pairs = []
    for i in range(len(shown)):
        for j in range(i + 1, len(shown)):
            a, b = shown[i]["box"], shown[j]["box"]
            if a.intersects(b) and a.intersection(b).area > 0.02 * min(a.area, b.area):
                pairs.append((shown[i]["id"], shown[j]["id"]))
    cb = 0
    for r in shown:
        for c in contour_boxes:
            if r["box"].intersects(c):
                cb += 1
                break
    cross = 0
    leaders = [(r["id"], LineString(r["leader"])) for r in rows if r.get("leader")]
    for r in shown:
        for lid, ln in leaders:
            if lid != r["id"] and ln.intersects(r["box"]):
                cross += 1
    per.sort(reverse=True)
    hidden = [r for r in rows if r["status"] == "hidden"]
    q = {
        "labels_shown": len(shown), "labels_hidden": len(hidden),
        "hidden_by_scale": sum(1 for r in hidden if r.get("why") == "scale"),
        "hidden_by_collision": sum(1 for r in hidden if r.get("why") == "collision"),
        "numbered": sum(1 for r in rows if r["status"] == "numbered"),
        "with_leader": sum(1 for r in rows if r.get("leader")), "pinned": sum(1 for r in rows if r.get("pinned")),
        "text_over_features_pct": round(100.0 * cov_a / tot_a, 1) if tot_a else 0.0,
        "over_features_by_kind_pct": {k_: round(100.0 * v / tot_a, 1) for k_, v in sorted(kinds.items())} if tot_a else {},
        "labels_over_25pct": over, "label_label_overlaps": len(pairs), "labels_over_contour_labels": cb, "leaders_crossing_other_labels": cross,
        "worst": [{"id": i, "text": t, "tier": ti, "over_pct": round(100 * f, 1), "by_kind": bk} for f, i, t, ti, bk in per[:8] if f > 0],
        "overlapping_pairs": pairs[:12],
        "hidden": [{"id": r["id"], "text": r["text"], "tier": r["tier"], "why": r.get("why")} for r in hidden if r.get("why") != "scale"][:40],
    }
    return q


def qa_text(q, title="Label QA"):
    out = [f"{title}: {q['labels_shown']} shown, {q['labels_hidden']} hidden ({q['hidden_by_scale']} by scale, {q['hidden_by_collision']} by collision), "
           f"{q['numbered']} numbered, {q['with_leader']} with leader, {q['pinned']} pinned",
           f"  text over map features: {q['text_over_features_pct']}% of text area "
           f"({', '.join(f'{k} {v}%' for k, v in q['over_features_by_kind_pct'].items()) or 'none'}); {q['labels_over_25pct']} labels over 25%",
           f"  label/label overlaps: {q['label_label_overlaps']}, over contour labels: {q['labels_over_contour_labels']}, leaders crossing other labels: {q['leaders_crossing_other_labels']}"]
    for w in q["worst"][:5]:
        out.append(f"  worst: {w['text']} ({w['tier']}) {w['over_pct']}% {w['by_kind']}")
    for h in q["hidden"][:8]:
        out.append(f"  hidden: {h['text']} ({h['tier']}, {h['why']})")
    return "\n".join(out)


# ------------------------------------------------------------------ legend
def legend_layout(entries, size, width_of, title=None, line=1.25):
    """entries: [(n, text)] -> (lines [(x_off, y_off, str, bold)], w, h) for one column block (page pt)."""
    lh = size * line
    rows, y = [], 0.0
    if title:
        rows.append((0.0, size * 0.95, title, True))
        y = lh * 1.35
    w = width_of(title) if title else 0.0
    nw = size * 2.1
    for n, t in entries:
        rows.append((0.0, y + size * 0.95, str(n), True))
        rows.append((nw, y + size * 0.95, t, False))
        w = max(w, nw + width_of(t))
        y += lh
    return rows, w + 2, y + size * 0.3


def legend_svg(rows, x0, y0, size, font_style, backing=None, pad=4.0, w=0.0, h=0.0):
    """-> list of svg strings: optional white backing rect, then the text rows (ids legend_<k>)."""
    from xml.sax.saxutils import escape
    out = []
    if backing:
        out.append(f'<rect id="legend_backing" x="{x0 - pad:.2f}" y="{y0 - pad:.2f}" width="{w + 2 * pad:.2f}" height="{h + 2 * pad:.2f}" rx="2" '
                   f'style="fill:{backing[0]};fill-opacity:{backing[1]:.2f};stroke:#1a1a1a;stroke-width:0.4"/>')
    for i, (dx, dy, t, bold) in enumerate(rows):
        fw = "bold" if bold else "normal"
        out.append(f'<text id="legend_{i}" x="{x0 + dx:.2f}" y="{y0 + dy:.2f}" font-size="{size:g}" text-anchor="start" '
                   f'style="{font_style};font-weight:{fw};fill:#111111">{escape(t)}</text>')
    return out


def marker_svg(id_, x, y, r, num, size, font_style, fill="#ffffff", ring="#1a1a1a"):
    from xml.sax.saxutils import escape
    return [f'<circle id="{id_}_marker" class="callout-marker" cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" style="fill:{fill};stroke:{ring};stroke-width:0.8"/>',
            f'<text id="{id_}_marknum" x="{x:.2f}" y="{y + size * 0.35:.2f}" font-size="{size:g}" text-anchor="middle" '
            f'style="{font_style};font-weight:bold;fill:{ring}">{escape(str(num))}</text>']


# ------------------------------------------------------------------ terrain contrast (optional)
def make_sampler(png_path):
    """-> f(x_ft0, y_ft0, x_ft1, y_ft1) -> mean luminance 0..1 of the shading PNG there, or None when unavailable.
    The PNG needs its .json sidecar (bounds_ft, width_px, height_px) as written by shading.py."""
    try:
        import numpy as np
        from PIL import Image
        meta = json.load(open(os.path.splitext(png_path)[0] + ".json", encoding="utf-8"))
        im = np.asarray(Image.open(png_path).convert("L"), float) / 255.0
        b = meta["bounds_ft"]
    except Exception:
        return None
    H, W = im.shape

    def f(x0, y0, x1, y1):
        sx, sy = W / (b["x_max"] - b["x_min"]), H / (b["y_max"] - b["y_min"])
        i0, i1 = sorted((int((x0 - b["x_min"]) * sx), int((x1 - b["x_min"]) * sx)))
        j0, j1 = sorted((int((y0 - b["y_min"]) * sy), int((y1 - b["y_min"]) * sy)))
        i0, j0, i1, j1 = max(i0, 0), max(j0, 0), min(max(i1, i0 + 1), W), min(max(j1, j0 + 1), H)
        if i1 <= i0 or j1 <= j0:
            return None
        return float(im[j0:j1, i0:i1].mean())
    return f


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["pin", "clear", "list"])
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--positions")
    ap.add_argument("--manifest")
    ap.add_argument("--ids", default="")
    a = ap.parse_args(argv)
    if a.cmd == "pin":
        pos = json.load(open(a.positions, encoding="utf-8"))
        man = json.load(open(a.manifest, encoding="utf-8"))
        n, na, moved = pin_positions(a.place, pos.get("labels", pos) if isinstance(pos, dict) else pos, man)
        print(json.dumps({"pinned": n, "anchors": na, "ids": moved, "total": len(load_overrides(a.place)), "file": overrides_path(a.place)}))
    elif a.cmd == "clear":
        n = clear_overrides(a.place, [i for i in a.ids.split(",") if i])
        print(json.dumps({"cleared": n, "total": len(load_overrides(a.place))}))
    else:
        print(json.dumps({"overrides": load_overrides(a.place)}))


if __name__ == "__main__":
    main()
