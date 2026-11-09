"""render_items.py (panel fast map edits): the outline / centreline of a few roads are identical to what render_world.py and road_edit.draw_svg write
(same id, same d), neighbours are found from the new and the old geometry, deleted / unknown ids are never drawn, and no world file is written.
Run: python illustrator/generators/test_render_items.py      (about 2 s, reads world/bridgehollow__dyers_walk_local, writes only to a temp folder)
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import render_items as RI  # noqa: E402
import render_world as RW  # noqa: E402

PLACE = "bridgehollow__dyers_walk_local"
FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        FAILS.append(name)


def paths(svg_file):
    t = open(svg_file, encoding="utf-8").read().replace("_x5F_", "_")
    out = {}
    for m in re.finditer(r'<g id="([^"]+)"[^>]*>|<path id="([^"]+)"[^>]*?\sd="([^"]+)"', t):
        if m.group(1):
            layer = m.group(1)
        else:
            out[(layer, m.group(2))] = m.group(3)
    return out


def main():
    world = os.path.join(RW.REPO, "world", PLACE)
    stamp = {f: os.path.getmtime(os.path.join(world, f)) for f in os.listdir(world) if f.endswith(".json")}
    with tempfile.TemporaryDirectory() as tmp:
        full, items = os.path.join(tmp, "full.svg"), os.path.join(tmp, "items.svg")
        subprocess.run([sys.executable, os.path.join(HERE, "render_world.py"), "--place", PLACE, "--out", full, "--svg-check", "off"], check=True, capture_output=True)
        out = subprocess.run([sys.executable, os.path.join(HERE, "render_items.py"), "--place", PLACE, "--ids", "str_016,str_020,nope_1", "--out", items],
                             check=True, capture_output=True, text=True).stdout
        r = json.loads(out.strip().splitlines()[-1])
        check("json: drawn / skipped", r["drawn"] == ["str_016", "str_020"] and r["skipped"] == ["nope_1"] and r["neighbours"] == [], r)
        a, b = paths(items), paths(full)
        roads = [k for k in a if k[0] == "Roads"]
        check("both outlines on layer Roads", sorted(k[1] for k in roads) == ["str_016", "str_020"], roads)
        check("outline d identical to render_world (same junction cuts, clip, page mapping)", all(a[k] == b.get(k) for k in roads), [k for k in roads if a[k] != b.get(k)])
        # centrelines: same as road_edit.draw_svg (object_edit draw-roads) with the panelio view
        import panelio
        from types import SimpleNamespace
        import road_edit
        view = panelio.cmd_view(SimpleNamespace(place=PLACE, view="town", preset=None, scale=None, grid=None, page=None, major=None, no_grid=False))
        cl = os.path.join(tmp, "cl.svg")
        road_edit.draw_svg(world, view, cl)
        c = paths(cl)
        cls = [k for k in a if k[0] == "Road Centerlines"]
        check("centrelines identical to draw-roads", len(cls) == 2 and all(a[k] == c.get(k) for k in cls), cls)
        # neighbours: a road touching str_020 (old geometry from --before-file when the road is gone)
        model = RW.load_place(PLACE)
        nb_now = RI.neighbours(model["streets"], ["str_020"])
        check("neighbours of a changed road (new geometry)", len(nb_now) > 0 and "str_020" not in nb_now, nb_now)
        rest = [s for s in model["streets"] if s["id"] != "str_020"]
        nb_gone = RI.neighbours(rest, [], before=model["streets"], gone=["str_020"])
        check("neighbours of a deleted road come from the old geometry", nb_gone == nb_now, (nb_gone, nb_now))
        check("a deleted id is never its own neighbour", "str_020" not in RI.neighbours(model["streets"], [], before=model["streets"], gone=["str_020"]))
        only = os.path.join(tmp, "only.svg")
        RI.main(["--place", PLACE, "--ids", "str_016", "--layers", "Road Centerlines", "--out", only])
        check("--layers limits the output", [k[0] for k in paths(only)] == ["Road Centerlines"], paths(only))
        try:
            RI.main(["--place", PLACE, "--ids", "str_016", "--layers", "Blocks", "--out", only])
            check("unknown layer refused", False)
        except SystemExit as e:
            check("unknown layer refused", e.code != 0)
    check("no world file written", all(os.path.getmtime(os.path.join(world, f)) == t for f, t in stamp.items()))
    print(f"{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
