"""Canonical layer stacking of the generated Illustrator documents (one source of truth).

Lists run TOP to BOTTOM, the way Illustrator's Layers panel shows them. render_world.SPEC is built from these; the SVG is
written bottom-first (lib_svg.LayerTree), so 'Label Backing' (halo copies / boxes) is always the first label group in the
file = painted under every label text layer, leader and callout.

presets/layer_order.json is written from this module (python layer_order.py --write) for the panel / host.jsx
(order_layers after a replace / redraw); generators/test_layer_order.py checks the file, render_world.SPEC and
panel/lib/core.js LABEL_LAYERS agree.
"""
import json
import os
import sys

BACKING = "Label Backing"
HIDDEN = "Labels - Hidden"

# sublayers of LABELS, top to bottom. Label Backing must stay LAST (bottom).
LABEL_LAYERS = ["Legend", "Callout Markers", "Leader Anchors", "Leaders", "Labels - Districts", "Labels - Streets",
                "Labels - Buildings", "Labels - Rooms", HIDDEN, "Labels - Elevation", BACKING]
# layers whose items are label text (the backing must be under all of them)
LABEL_TEXT_LAYERS = ["Labels - Districts", "Labels - Streets", "Labels - Buildings", "Labels - Rooms", "Labels - Elevation", HIDDEN]

# top-level layers, top to bottom
TOP_LAYERS = ["NOTES", "LABELS", "FOUNDRY MARKERS", "ART - Top", "ART - Fills", "ART - Textures", "ART - Masks", "LINES", "GUIDES"]
LINES_LAYERS = ["Walls", "Buildings", "Blocks", "Roads", "Water", "Terrain", "Fences", "Details", "DETAILS - Lots", "DETAILS - Trees"]
TERRAIN_LAYERS = ["Contours - Minor", "Contours - Index"]
GUIDE_LAYERS = ["Grid", "Scale bar", "North arrow", "Bounds"]

# what the panel's order_layers step enforces: each list is one parent's children, top to bottom
ORDER_GROUPS = [LABEL_LAYERS, ["NOTES", "LABELS", "LINES"]]

JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "presets", "layer_order.json")


def as_json():
    return {
        "_note": "Canonical layer stacking, TOP to BOTTOM as in Illustrator's Layers panel. Written by illustrator/generators/layer_order.py "
                 "(do not edit by hand). 'Label Backing' (label halos / boxes) must be the bottom sublayer of LABELS, under every label text layer.",
        "top": TOP_LAYERS,
        "LABELS": LABEL_LAYERS,
        "LINES": LINES_LAYERS,
        "Terrain": TERRAIN_LAYERS,
        "GUIDES": GUIDE_LAYERS,
        "label_text_layers": LABEL_TEXT_LAYERS,
        "backing": BACKING,
        "order_groups": ORDER_GROUPS,
    }


def write(path=JSON_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(as_json(), f, indent=1)
        f.write("\n")
    return os.path.abspath(path)


def backing_below_text(names_top_to_bottom):
    """True when BACKING comes after (= below) every label text layer present in a top-to-bottom name list."""
    if BACKING not in names_top_to_bottom:
        return True
    b = names_top_to_bottom.index(BACKING)
    return all(names_top_to_bottom.index(n) < b for n in LABEL_TEXT_LAYERS if n in names_top_to_bottom)


assert LABEL_LAYERS[-1] == BACKING and backing_below_text(LABEL_LAYERS)

if __name__ == "__main__":
    if "--write" in sys.argv:
        print("wrote", write())
    else:
        print(json.dumps(as_json(), indent=1))
