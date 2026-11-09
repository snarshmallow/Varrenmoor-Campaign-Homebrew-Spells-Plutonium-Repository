"""Orientation of every terrain / map / foliage preview producer (orient_check.py): north up, east right, world feet x east / y south.
    python illustrator/generators/test_orient.py      (or pytest)"""
import json
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import orient_check as O  # noqa: E402


def test_all_producers_identity():
    with tempfile.TemporaryDirectory() as t:
        rows = O.check_all(t, None)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, bad
    assert len(rows) >= 18


def test_decoder_finds_planted_transforms():
    truth = O.synth_heights()
    for name, f in O.TRANSFORMS.items():
        got, _ = O.best_transform(f(truth), truth)
        assert got == name, (name, got)


def test_real_place_river_in_valley():
    place = "mountain_pass_fort_town"
    if not os.path.exists(os.path.join(O.REPO, "world", place, "water.json")):
        return
    with tempfile.TemporaryDirectory() as t:
        rows = O.check_real(t, place)          # copies the place to a temp root; world/ is only read
    r = rows[-1]
    assert r["transform"] == "identity", r


def test_preview_features_and_foliage_frame():
    import heightmap_paint as HP
    import foliage as FO
    with tempfile.TemporaryDirectory() as t:
        root = os.path.join(t, "world")
        O.make_synth(root)
        f = HP.preview_features(O.PLACE, root)
        b = np.array(f["buildings"][0]["polygon"])
        assert b[:, 0].mean() > O.W_FT / 2 and b[:, 1].mean() < O.H_FT / 2          # NE
        assert f["roads"][0]["points"][0][1] > O.H_FT * 0.9                            # south edge
        assert f["water"][0]["closed"] and f["water"][0]["points"][0][0] > O.W_FT / 2   # east
        pv = HP.export_preview(O.PLACE, root=root, wdir=os.path.join(t, "w"), max_px=100, bin_dir=os.path.join(t, "bin"), layer="base")
        assert pv["ok"] and os.path.exists(os.path.join(t, "bin", "preview_features.json"))
        env = FO.Env.from_place(O.PLACE, root=os.path.join(root, O.PLACE))
        doc = FO.FoliageDoc(O.PLACE, path=os.path.join(t, "f.json"), data={})
        png = FO.preview_png(doc, FO._lib(), env, os.path.join(t, "p.png"), max_px=320, frame_ft=[1200, 100, 1500, 300])
        rgb = O.img_lum(png)
        red = O.colour_mask(rgb, (220, 30, 30), 2)
        ys, xs = np.nonzero(red)
        s = rgb.shape[1] / O.W_FT
        assert abs(xs.min() / s - 1200) < 8 and abs(ys.max() / s - 300) < 8          # map window frame drawn at its feet position
        # light from the north-west: the NW flank of the NE peak is brighter than its SE flank
        lum = rgb[..., :3].mean(-1)
        px, py = int(O.PEAK[0] * s), int(O.PEAK[1] * s)
        d = int(80 * s)
        assert lum[py - d, px - d] > lum[py + d, px + d]


if __name__ == "__main__":
    n = 0
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            n += 1
            print("PASS", k)
    print(f"{n} passed")
