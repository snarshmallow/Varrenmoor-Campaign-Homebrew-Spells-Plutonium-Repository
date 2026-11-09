"""Bridgehollow building styles by ring tier: writes ONLY the `style` key of world/bridgehollow/buildings/*.json (never geometry). Idempotent, deterministic.

Tiers (from world/bridgehollow/districts.json; the rings come from town_params.json ring_spec):
  warden  = inside the Authority Ward polygon (dis_authority, ring "authority": the Warden's Hall, Wardens' Barracks, court, records, treasury, lockup) -> the Warden's Ring
  inner   = Commoners' Ring (dis_commoner) buildings whose centre lies within --inner-ft (default 60 ft, about one commoner street spacing) of the Authority Ward edge
  other   = the rest of the Commoners' Ring and the Farmland: left exactly as they are (no style key = the current look); a bh_* style left there by an earlier run is removed
Styles: warden house/inn -> bh_warden_house, warden civic -> bh_warden_civic, inner house/craft -> bh_inner_house, sheds/stables in either tier -> bh_ring_outbuilding.
--season winter picks the *_winter variants (snow on roofs and dormers). A building whose style was set by hand to a non-bh preset is never touched.

  python illustrator/generators/bridgehollow_styles.py [--dry] [--season none|winter] [--inner-ft 60] [--clear] [--place bridgehollow]
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import building_styles as bs  # noqa: E402

TIER_STYLE = {("warden", "house"): "bh_warden_house", ("warden", "inn"): "bh_warden_house", ("warden", "civic"): "bh_warden_civic",
              ("warden", "craft"): "bh_warden_house", ("warden", "shed"): "bh_ring_outbuilding", ("warden", "stable"): "bh_ring_outbuilding",
              ("warden", "barn"): "bh_ring_outbuilding", ("inner", "house"): "bh_inner_house", ("inner", "craft"): "bh_inner_house", ("inner", "inn"): "bh_inner_house",
              ("inner", "civic"): "bh_warden_civic", ("inner", "shed"): "bh_ring_outbuilding", ("inner", "stable"): "bh_ring_outbuilding", ("inner", "barn"): "bh_ring_outbuilding"}


def tiers(place="bridgehollow", inner_ft=60.0):
    """{building id: (tier, kind)} for every building of the place."""
    from shapely.geometry import Polygon
    wd = bs._world_dir(place)
    with open(os.path.join(wd, "districts.json"), encoding="utf-8") as f:
        ds = {d["id"]: d for d in json.load(f)["districts"]}
    auth = Polygon(ds["dis_authority"]["geometry"]["points"])
    comm = Polygon(ds["dis_commoner"]["geometry"]["points"]) if "dis_commoner" in ds else None
    out = {}
    for p, b in bs._iter_buildings(place):
        pts = b["geometry"]["points"]
        c = Polygon(pts).centroid if len(pts) >= 3 else None
        tier = "other"
        if c is not None and auth.contains(c):
            tier = "warden"
        elif c is not None and comm is not None and comm.contains(c) and auth.exterior.distance(c) <= inner_ft:
            tier = "inner"
        out[b["id"]] = (tier, b.get("kind") or "house")
    return out


def style_for(tier, kind, season="none"):
    sid = TIER_STYLE.get((tier, kind))
    if sid and season == "winter":
        sid += "_winter"
    return sid


def is_ours(sid):
    return isinstance(sid, str) and sid.startswith("bh_")


def apply(place="bridgehollow", season="none", inner_ft=60.0, dry=False, clear=False):
    pres = bs.load_presets()
    T = tiers(place, inner_ft)
    changed, counts, styles = [], {}, {}
    for p, b in bs._iter_buildings(place):
        tier, kind = T[b["id"]]
        counts[tier] = counts.get(tier, 0) + 1
        cur = b.get("style")
        if cur and not is_ours(cur):
            styles[b["id"]] = cur                             # a hand-picked style stays
            continue
        want = None if clear else style_for(tier, kind, season)
        if want and want not in pres:
            raise SystemExit(f"preset {want} missing")
        if want:
            styles[b["id"]] = want
        if cur == want:
            continue
        if want:
            b["style"] = want
        else:
            b.pop("style", None)
        changed.append(b["id"])
        if not dry:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(b, f, indent=1, ensure_ascii=False)
                f.write("\n")
    per_style = {}
    for s in styles.values():
        per_style[s] = per_style.get(s, 0) + 1
    return {"place": place, "season": season, "inner_ft": inner_ft, "dry": dry, "tiers": counts, "styles": per_style, "changed": changed, "count": len(changed)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--season", choices=["none", "winter"], default="none")
    ap.add_argument("--inner-ft", type=float, default=60.0)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--clear", action="store_true", help="remove every bh_* style (back to the current look)")
    ap.add_argument("--world-root")
    a = ap.parse_args(argv)
    if a.world_root:
        os.environ["VB_WORLD_ROOT"] = a.world_root
    r = apply(a.place, a.season, a.inner_ft, a.dry, a.clear)
    print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
