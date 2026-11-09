"""Regression: tree crowns must not be clipped.  python illustrator/generators/test_foliage_crowns.py
Root cause of the cut-off tops: the LOD2 impostor tiles were painted past the tile edge (alpha touched row 0 and column 0/255) and the billboard was
only as tall as the nominal height, shorter than the LOD0 crown.  Now the sprites keep a margin and the card is sized from the LOD0 bounds."""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foliage_mesh as fm  # noqa: E402
import foliage_tex as ft  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


S = fm.TILE_PX
for season in ("summer", "autumn", "winter"):
    for name, fn in (("imp_conifer", ft.paint_imp_conifer), ("imp_broad", ft.paint_imp_broad)):
        for seed in (1, 11, 42):
            a = fn(S, np.random.default_rng(seed), season)[..., 3] > 8
            check(f"{name} {season} seed {seed}: no opaque pixel on the top/left/right edge", not (a[:3].any() or a[:, :3].any() or a[:, -3:].any()),
                  f"top={a[:3].sum()} left={a[:, :3].sum()} right={a[:, -3:].sum()}")
lib = fm.FoliageLibrary()
n = 0
for sid, sp in lib.species.items():
    if sp["kind"] in ("ground", "prop", "rock"):
        continue
    m0, m2 = lib.mesh(sid, 0, 0), lib.mesh(sid, 0, 2)
    V0, V2 = np.asarray(m0.V, float).reshape(-1, 3), np.asarray(m2.V, float).reshape(-1, 3)
    if not len(V0) or not len(V2):
        continue
    n += 1
    check(f"{sid}: LOD2 card is at least as tall as the LOD0 crown", V2[:, 2].max() >= V0[:, 2].max() - 1e-6, f"{V2[:, 2].max():.2f} < {V0[:, 2].max():.2f}")
    check(f"{sid}: LOD2 card is at least as wide as the LOD0 crown", np.abs(V2[:, :2]).max() >= np.abs(V0[:, :2]).max() - 1e-6)
    check(f"{sid}: LOD2 card does not start below the ground", V2[:, 2].min() > -0.5)
check("trees and shrubs covered", n >= 10, str(n))
print("\n%d failed" % len(fails) if fails else "\nall crown tests passed")
sys.exit(1 if fails else 0)
