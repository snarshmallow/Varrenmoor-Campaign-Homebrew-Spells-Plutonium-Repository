"""SVG sanity check for the layered SVGs our generators write (render_world.py, place_render.py, Redraw labels).

Illustrator imports SVG synchronously and has no progress / cancel: content that is merely slow in a browser can lock it
(Application Hang). This checks the things that can do that, plus the label z-order (halos / backing strictly under text):

  - invalid XML, duplicated ids
  - NaN / inf anywhere in numbers, coordinates far off the page (a label at 1e9), zero / negative / huge font sizes
  - points per path (one huge polyline), curved-label baselines (<textPath> or <svg>.curved.json) with too many points
  - <textPath> in the SVG (Illustrator shows a modal "Text on Path will be Flattened" dialog: looks exactly like a hang
    when a script drives the import)
  - text elements per layer / in total, empty text, font families, small-caps tspans
  - filters, masks, clipPaths, gradients, patterns (and their nesting depth)
  - layer order: 'Label Backing' before (= under) every label text layer, every '<id>_halo' before its '<id>' text

  python illustrator/generators/svg_sanity.py FILE.svg [--json] [--strict]     exit 1 on errors (--strict: also on warnings)

In code: rep = svg_sanity.check(path); print(svg_sanity.summary(rep)); rep["errors"], rep["warnings"], rep["layers"].
"""
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import layer_order as lo  # noqa: E402

SVG_NS = "{http://www.w3.org/2000/svg}"
INK_NS = "{http://www.inkscape.org/namespaces/inkscape}"

LIMITS = {
    "text_total_warn": 800, "text_total_error": 3000,         # text frames Illustrator creates on import (halo copies count)
    "text_layer_warn": 500, "text_layer_error": 2000,
    "points_path_warn": 5000, "points_path_error": 60000,     # vertices in one path
    "points_curved_warn": 40, "points_curved_error": 400,     # vertices of one curved label baseline
    "bytes_warn": 8_000_000, "bytes_error": 60_000_000,
    "coord_abs_error": 100000.0,                              # |x| or |y| beyond this (pt) = broken geometry
    "page_slack": 1.0,                                        # coordinates up to this many page sizes outside the page are tolerated
    "font_size_min": 0.5, "font_size_max": 400.0,
    "font_families_warn": 6,
    "clip_depth_error": 3,
}

NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
BAD_NUM = re.compile(r"(?<![A-Za-z#])(?:nan|inf|infinity)(?![A-Za-z])", re.I)
BAD_NUM_ATTR = re.compile(r"nan|inf", re.I)
FONT_FAM = re.compile(r"font-family\s*:\s*([^;\"]+)")
STROKE = re.compile(r"(?:^|;)\s*stroke\s*:\s*(?!none)[^;]+")
NUM_ATTRS = ("x", "y", "cx", "cy", "r", "rx", "ry", "width", "height", "x1", "y1", "x2", "y2", "dx", "dy", "font-size", "transform", "points", "d")
LABEL_TEXT_LAYERS = set(lo.LABEL_TEXT_LAYERS)


def _tag(el):
    return el.tag.split("}")[-1]


def _is_layer(el):
    return _tag(el) == "g" and (el.get(INK_NS + "groupmode") == "layer" or el.get("{http://ns.adobe.com/AdobeIllustrator/10.0/}layer") == "yes")


def _layer_name(el):
    return el.get(INK_NS + "label") or el.get("id") or "?"


def _decode_id(s):
    return (s or "").replace("_x5F_", "_")


def _num_list(s):
    return [float(m) for m in NUM.findall(s or "")]


def _halo_like(el):
    st = el.get("style") or ""
    return (el.get("id") or "").replace("_x5F_", "_").endswith("_halo") or (STROKE.search(st) is not None and _tag(el) == "text")


def check(src, limits=None, page=None):
    """src: path of an SVG, or the SVG text. Returns a report dict:
    {ok, errors[], warnings[], bytes, page:[w,h], layers:{name:{text, halo, path, other, points_max}}, layer_order:[...], totals:{...}, fonts:[...]}"""
    L = dict(LIMITS, **(limits or {}))
    errors, warnings = [], []
    if isinstance(src, str) and src.lstrip().startswith("<"):
        text, path = src, None
    else:
        path = src
        with open(src, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    nbytes = len(text.encode("utf-8"))
    rep = {"ok": False, "file": path, "errors": errors, "warnings": warnings, "bytes": nbytes, "layers": {}, "layer_order": [], "fonts": [],
           "totals": {}, "page": None}
    if nbytes > L["bytes_error"]:
        errors.append(f"file is {nbytes / 1e6:.1f} MB (limit {L['bytes_error'] / 1e6:.0f} MB)")
    elif nbytes > L["bytes_warn"]:
        warnings.append(f"file is {nbytes / 1e6:.1f} MB: slow to import")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        errors.append(f"invalid XML: {e}")
        return rep
    vb = _num_list(root.get("viewBox"))
    if page:
        W, H = page
    elif len(vb) == 4:
        W, H = vb[2], vb[3]
    else:
        W, H = _num_list(root.get("width"))[:1] + [0], _num_list(root.get("height"))[:1] + [0]
        W, H = W[0] or 1224.0, H[0] or 792.0
    rep["page"] = [W, H]
    sl = L["page_slack"]
    xlo, xhi, ylo, yhi = -W * sl, W * (1 + sl), -H * sl, H * (1 + sl)

    ids, dup = {}, set()
    fonts = set()
    tot = {"text": 0, "halo": 0, "textpath": 0, "tspan": 0, "small_caps_tspan": 0, "paths": 0, "points": 0, "points_max": 0, "filters": 0, "masks": 0,
           "clippaths": 0, "gradients": 0, "patterns": 0, "images": 0, "empty_text": 0, "nan": 0, "off_page": 0, "far": 0, "box": 0}
    order = []                  # (doc index, element id, layer name, is_halo) for text elements
    layer_first = {}            # layer name -> document index of the layer group
    bad_coord_examples, far_examples, off_examples = [], [], []
    idx = [0]

    def walk(el, layer, clip_depth):
        idx[0] += 1
        i = idx[0]
        tg = _tag(el)
        if _is_layer(el):
            layer = _layer_name(el)
            layer_first.setdefault(layer, i)
            rep["layer_order"].append(layer)
            rep["layers"].setdefault(layer, {"text": 0, "halo": 0, "path": 0, "other": 0, "points_max": 0})
        lr = rep["layers"].setdefault(layer, {"text": 0, "halo": 0, "path": 0, "other": 0, "points_max": 0}) if layer else None
        eid = el.get("id")
        if eid:
            if eid in ids:
                dup.add(eid)
            ids[eid] = i
        # numbers: NaN / inf / far off the page
        for a in NUM_ATTRS:
            v = el.get(a)
            if v is None:
                continue
            if BAD_NUM_ATTR.search(v):          # numeric attributes hold no words: any nan / inf is a broken number (also 'Lnan,3')
                tot["nan"] += 1
                if len(bad_coord_examples) < 5:
                    bad_coord_examples.append(f"{eid or tg} {a}={v[:60]}")
                continue
            if a in ("d", "points"):
                ns = _num_list(v)
                xs, ys = ns[0::2], ns[1::2]
                npts = len(ys)
                tot["paths"] += 1
                tot["points"] += npts
                tot["points_max"] = max(tot["points_max"], npts)
                if lr is not None:
                    lr["points_max"] = max(lr["points_max"], npts)
                if npts > L["points_path_error"]:
                    errors.append(f"path {_decode_id(eid)} in '{layer}' has {npts} points (limit {L['points_path_error']})")
                elif npts > L["points_path_warn"]:
                    warnings.append(f"path {_decode_id(eid)} in '{layer}' has {npts} points")
                if any(abs(q) > L["coord_abs_error"] for q in ns):
                    tot["far"] += 1
                    far_examples.append(f"{_decode_id(eid) or tg} {a} spans {min(ns):.0f}..{max(ns):.0f}")
                elif (xs and (min(xs) < xlo or max(xs) > xhi)) or (ys and (min(ys) < ylo or max(ys) > yhi)):
                    tot["off_page"] += 1
                    off_examples.append(f"{_decode_id(eid) or tg} {a} spans {min(ns):.0f}..{max(ns):.0f}")
            elif a in ("x", "y", "cx", "cy", "x1", "x2", "y1", "y2"):
                ns = _num_list(v)
                lo_, hi_ = (xlo, xhi) if a.startswith(("x", "cx")) else (ylo, yhi)
                if any(abs(q) > L["coord_abs_error"] for q in ns):
                    tot["far"] += 1
                    far_examples.append(f"{_decode_id(eid) or tg} {a}={v[:40]}")
                elif any(q < lo_ or q > hi_ for q in ns):
                    tot["off_page"] += 1
                    off_examples.append(f"{_decode_id(eid) or tg} {a}={v[:40]}")
            elif a == "font-size":
                ns = _num_list(v)
                if ns and not (L["font_size_min"] <= ns[0] <= L["font_size_max"]):
                    errors.append(f"text {_decode_id(eid)} font-size {v}")
            elif a == "transform":
                if any(abs(q) > L["coord_abs_error"] for q in _num_list(v)):
                    tot["far"] += 1
                    far_examples.append(f"{_decode_id(eid) or tg} transform={v[:40]}")
        st = el.get("style") or ""
        if BAD_NUM.search(st):
            tot["nan"] += 1
        for m in FONT_FAM.finditer(st):
            fonts.add(m.group(1).strip())
        if el.get("font-family"):
            fonts.add(el.get("font-family").strip())
        if tg == "text":
            halo = _halo_like(el)
            tot["text"] += 1
            tot["halo"] += 1 if halo else 0
            if lr is not None:
                lr["text"] += 1
                lr["halo"] += 1 if halo else 0
            if not "".join(el.itertext()).strip():
                tot["empty_text"] += 1
            if el.find(SVG_NS + "textPath") is not None:
                tot["textpath"] += 1
            for ts in el.iter(SVG_NS + "tspan"):
                tot["tspan"] += 1
                if ts.get("font-size"):
                    tot["small_caps_tspan"] += 1
            order.append((i, _decode_id(eid), layer, halo))
        elif tg in ("path", "polyline", "polygon", "line"):
            if lr is not None:
                lr["path"] += 1
        elif tg == "rect" and (el.get("id") or "").replace("_x5F_", "_").endswith("_box"):
            tot["box"] += 1
        elif tg not in ("g", "style", "tspan", "textPath") and lr is not None:
            lr["other"] += 1
        tot["filters"] += tg == "filter" or ("filter" in st and "url(" in st)
        tot["gradients"] += tg in ("linearGradient", "radialGradient")
        tot["patterns"] += tg == "pattern"
        tot["images"] += tg == "image"
        cd = clip_depth
        if tg in ("mask", "clipPath") or el.get("mask") or el.get("clip-path"):
            tot["masks" if (tg == "mask" or el.get("mask")) else "clippaths"] += 1
            cd += 1
            if cd > L["clip_depth_error"]:
                errors.append(f"clip / mask nested {cd} deep at {_decode_id(eid) or tg}")
        for ch in el:
            if _tag(ch) == "style":
                continue
            walk(ch, layer, cd)

    walk(root, None, 0)
    if dup:
        errors.append(f"{len(dup)} duplicated id(s), e.g. {sorted(dup)[:3]}")
    if tot["nan"]:
        errors.append(f"{tot['nan']} NaN / inf value(s): {bad_coord_examples[:3]}")
    if tot["far"]:
        errors.append(f"{tot['far']} element(s) with coordinates beyond {L['coord_abs_error']:g} pt (broken geometry): {far_examples[:3]}")
    if tot["off_page"]:
        warnings.append(f"{tot['off_page']} element(s) reach more than a page outside the {W:g}x{H:g} pt page: {off_examples[:3]}")
    if tot["textpath"]:
        errors.append(f"{tot['textpath']} <textPath> label(s): Illustrator flattens them behind a modal dialog on import (use --curved-text host)")
    if tot["text"] > L["text_total_error"]:
        errors.append(f"{tot['text']} text elements (limit {L['text_total_error']}): lower the label budget")
    elif tot["text"] > L["text_total_warn"]:
        warnings.append(f"{tot['text']} text elements: slow to import / replace in Illustrator")
    for nm, lr in rep["layers"].items():
        if lr["text"] > L["text_layer_error"]:
            errors.append(f"layer '{nm}' has {lr['text']} text elements (limit {L['text_layer_error']})")
        elif lr["text"] > L["text_layer_warn"]:
            warnings.append(f"layer '{nm}' has {lr['text']} text elements")
    if tot["empty_text"]:
        warnings.append(f"{tot['empty_text']} empty text element(s)")
    if tot["filters"] or tot["masks"] or tot["patterns"] or tot["images"]:
        warnings.append(f"filters {tot['filters']}, masks {tot['masks']}, patterns {tot['patterns']}, images {tot['images']} (slow to import)")
    if len(fonts) > L["font_families_warn"]:
        warnings.append(f"{len(fonts)} font families: {sorted(fonts)}")
    # z-order: backing under text
    for msg in order_problems(layer_first, order):
        errors.append(msg)
    rep["fonts"] = sorted(fonts)
    rep["totals"] = tot
    rep["ok"] = not errors
    if path:
        cj = path + ".curved.json"
        if os.path.exists(cj):
            check_curved(cj, L, rep)
    return rep


def order_problems(layer_first, order):
    """Halos / backing must sit under the text: the 'Label Backing' layer before every label text layer in the document,
    and inside one layer every <id>_halo before <id>."""
    out = []
    bk = layer_first.get(lo.BACKING)
    if bk is not None:
        above = [n for n in LABEL_TEXT_LAYERS if n in layer_first and layer_first[n] < bk]
        if above:
            out.append(f"'{lo.BACKING}' is drawn above {above}: halos would cover the text")
    pos = {eid: (i, layer) for i, eid, layer, halo in order if not halo}
    bad = []
    for i, eid, layer, halo in order:
        if halo and eid.endswith("_halo"):
            t = pos.get(eid[:-5])
            if t and t[0] < i:
                bad.append(eid)
    if bad:
        out.append(f"{len(bad)} halo(s) drawn after their text, e.g. {bad[:3]}")
    return out


def check_curved(cj, L, rep):
    try:
        data = json.load(open(cj, encoding="utf-8"))
    except Exception as e:      # noqa: BLE001
        rep["errors"].append(f"{os.path.basename(cj)}: unreadable ({e})")
        rep["ok"] = False
        return
    items = data.get("items") or []
    mx = max((len(it.get("points") or []) for it in items), default=0)
    rep["totals"]["curved"] = len(items)
    rep["totals"]["curved_points_max"] = mx
    for it in items:
        pts = it.get("points") or []
        if any((not math.isfinite(float(c))) for p in pts for c in p):
            rep["errors"].append(f"curved label {it.get('id')}: NaN / inf in its path")
        if len(pts) > L["points_curved_error"]:
            rep["errors"].append(f"curved label {it.get('id')}: {len(pts)} points on its baseline (limit {L['points_curved_error']})")
        elif len(pts) > L["points_curved_warn"]:
            rep["warnings"].append(f"curved label {it.get('id')}: {len(pts)} points on its baseline")
    rep["ok"] = not rep["errors"]


def summary(rep):
    t = rep.get("totals") or {}
    lab = {k: v["text"] for k, v in (rep.get("layers") or {}).items() if v.get("text")}
    head = (f"svg check: {'OK' if rep['ok'] else 'ERRORS'} - {rep['bytes'] / 1024:.0f} KB, {t.get('text', 0)} text ({t.get('halo', 0)} halos, "
            f"{t.get('box', 0)} boxes), {t.get('paths', 0)} paths / {t.get('points', 0)} points (max {t.get('points_max', 0)} in one path), "
            f"curved {t.get('curved', 0)} (max {t.get('curved_points_max', 0)} pts), textPath {t.get('textpath', 0)}, fonts {rep.get('fonts')}")
    lines = [head, "  text per layer: " + ", ".join(f"{k} {v}" for k, v in lab.items())]
    lines += ["  ERROR: " + e for e in rep["errors"]] + ["  warning: " + w for w in rep["warnings"]]
    return "\n".join(lines)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("svg", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    a = ap.parse_args(argv)
    bad = False
    for p in a.svg:
        rep = check(p)
        print(json.dumps(rep, indent=1) if a.json else (p + "\n" + summary(rep)))
        bad = bad or not rep["ok"] or (a.strict and rep["warnings"])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
