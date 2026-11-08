"""Texture audit: seam visibility, tiling repetition, texel density and PBR consistency of the procedural/preset textures.

    python textures_audit.py                 # table + contact sheet of the current state -> out/textures_audit/
    python textures_audit.py --tag before    # same with a name tag (before.png / after.png)
    python textures_audit.py --raw           # evaluate with the conditioning pass off (the "before" state)

Metrics (all on the albedo unless noted):
  seam    edge step / typical neighbour step, columns and rows (1.0 = no visible seam; > 2 = seam shows when tiled)
  macro   std of the 8x8 block means / std of the pixels (high = large blotches that make the repeat obvious)
  ppf     texels per foot at the catalogue tile size (texel density)
  nrm     RMS of the normal map's xy tilt (0 = flat map)   rgh  std of the roughness map G channel (0 = uniform)
One albedo at a time, 512 px each: light on RAM.
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import worldpack_pbr as pbr  # noqa: E402

OUT = os.path.join(HERE, "..", "out", "textures_audit")

# groups of materials worth checking (ids from worldpack_pbr.CATALOG plus dynamic style materials with a sample colour)
GROUPS = {
    "walls": ["mat_plank", "mat_plaster", "mat_wall_frame", "mat_wall_stone", "mat_wall_batten", "mat_s_brick_8a4a3a", "mat_s_board_8c3a2c",
              "mat_s_clap_a89878", "mat_s_log_7a5a38", "mat_s_beam_3a2a1c", "mat_s_plaster_d8cdb4", "mat_w_plank"],
    "roofs": ["mat_shingle", "mat_thatch", "mat_slate", "mat_red_tile", "mat_timber_roof", "mat_w_roof_snow", "mat_s_turf_5a7a3a"],
    "roads": ["mat_cobble", "mat_w_cobble", "mat_gravel", "mat_dirt", "mat_packed_earth", "mat_stone_slab", "mat_kerb"],
    "ground": ["mat_grass", "mat_rock", "mat_snow", "mat_w_rock", "mat_w_snow"],
    "water": ["mat_water", "mat_w_water", "mat_w_ice"],
}


def evaluate(mid, raw=False):
    c = pbr.info(mid)
    bt = pbr.base_texture(mid, raw=raw)
    if bt is None:
        return None
    alb, h = bt
    a = np.clip(alb, 0, 255)
    nm = pbr.normal_map(h, c["n"]) if c.get("n", 0) > 0 else None
    mr = pbr.mr_map(h, c["rough"], 0.3, c.get("metal", 0.0), micro=0.0 if raw else 0.12, wet=bool(c.get("wet"))) if c.get("mr") else None
    rec = dict(id=mid, px=a.shape[0], ppf=round(a.shape[0] / pbr.tile_ft(mid), 1), seam=round(float(pbr.seam_ratio(a)), 2), macro=round(pbr.macro_ratio(a), 2),
               nrm=round(float(np.sqrt((((nm[..., :2].astype(float) / 255 * 2 - 1) ** 2).sum(-1)).mean())), 3), has_nrm=nm is not None,
               rgh=round(float(mr[..., 1].std() / 255), 3) if mr is not None else None, rough=c["rough"])
    return a, rec


def sheet(items, path, cols=6, cell=224, title=""):
    from PIL import Image, ImageDraw
    rows = (len(items) + cols - 1) // cols
    im = Image.new("RGB", (cols * cell, rows * (cell + 22) + 24), (30, 30, 30))
    d = ImageDraw.Draw(im)
    d.text((6, 6), title, fill=(255, 255, 255))
    for i, (name, a, note) in enumerate(items):
        x, y = (i % cols) * cell, 24 + (i // cols) * (cell + 22)
        t = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).resize((cell // 2, cell // 2), Image.LANCZOS)
        for k in range(4):                                  # 2 x 2 repeats show the seams and the repeat
            im.paste(t, (x + (k % 2) * (cell // 2), y + (k // 2) * (cell // 2)))
        d.text((x + 3, y + cell + 1), (name + " " + note)[:int(cell / 6)], fill=(235, 235, 235))
    im.save(path)


def padding_sheet(n=1024, kinds=("meadow", "forest_floor", "scree", "heather_moor", "summer", "autumn")):
    """Contact sheet of the padding table tiles: each shown as a 2x2 repeat (seams), with the numeric wrap/edge ratio of the full-size tile."""
    import padding_textures as pt
    items, rows = [], []
    P = pt.list_texture_presets()
    for k in kinds:
        img, mean = pt.table_tile(P[k], n=n, seed=11)
        r = pbr.seam_ratio(img)
        rows.append(dict(id=k, px=n, seam_ratio=round(float(r), 3), edge_max_abs_diff=int(max(np.abs(img[:, 0].astype(int) - img[:, -1]).max(), np.abs(img[0].astype(int) - img[-1]).max())), mean=mean))
        items.append((k, img, f"seam {r:.2f}"))
        print(rows[-1])
    with open(os.path.join(OUT, "padding_tiles_metrics.json"), "w") as f:
        json.dump(rows, f, indent=1)
    sheet(items, os.path.join(OUT, "padding_tiles_sheet.png"), cols=3, cell=448, title="padding table tiles, 2x2 repeats; seam = step across the wrap / p90 of the per-line neighbour steps (about 1 or less = invisible)")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="current")
    ap.add_argument("--padding", action="store_true", help="only the padding table tiles sheet")
    ap.add_argument("--raw", action="store_true", help="conditioning off (before state)")
    a = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)
    if a.padding:
        return padding_sheet()
    rows, items = [], []
    for g, ids in GROUPS.items():
        for mid in ids:
            r = evaluate(mid, raw=a.raw)
            if r is None:
                continue
            alb, rec = r
            rec["group"] = g
            rows.append(rec)
            items.append((mid[4:], alb, f"s{rec['seam']} m{rec['macro']}"))
    with open(os.path.join(OUT, f"metrics_{a.tag}.json"), "w") as f:
        json.dump(rows, f, indent=1)
    sheet(items, os.path.join(OUT, f"sheet_{a.tag}.png"), title=f"{a.tag}: 2x2 repeats, s = seam ratio, m = macro blotchiness")
    print("%-24s %5s %5s %5s %5s %6s %5s" % ("id", "px", "ppf", "seam", "macro", "nrm", "rgh"))
    for r in rows:
        print("%-24s %5d %5.1f %5.2f %5.2f %6s %5s" % (r["id"], r["px"], r["ppf"], r["seam"], r["macro"], r["nrm"] if r["has_nrm"] else "-", r["rgh"] if r["rgh"] is not None else "-"))


if __name__ == "__main__":
    main()
