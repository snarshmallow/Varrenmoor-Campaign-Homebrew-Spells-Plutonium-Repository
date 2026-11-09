"""Foundation skirt tests (python test_foundation.py): the buried wall below the floor line is stone (style plinth material, else mat_wall_stone), has
world-feet UVs, reaches the skirt depth, and is present under doors (no untextured plaster box)."""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import building_styles as bs  # noqa: E402
import building_styles_preview as bsp  # noqa: E402
import test_building_styles as tbs  # noqa: E402
import worldpack_detail as wd  # noqa: E402
import worldpack_mesh as wm  # noqa: E402

FT = wm.FT


def _below(m, e, pk, mat_ids):
    zf = (e["base_elevation_ft"] - pk.frame.z_origin_ft) * FT
    z0 = zf - e["skirt_depth_ft"] * FT
    out = {}
    for k, F in m.subs.items():
        if not len(F):
            continue
        Z = m.V[F][:, :, 2]
        sel = np.all(Z <= zf + 1e-4, axis=1) & np.any(Z < zf - 1e-3, axis=1)
        if sel.any():
            out[k] = (F[sel], z0, zf)
    return out


class Foundation(unittest.TestCase):
    def _check(self, e, m, mat):
        pk = tbs.pack()
        parts = _below(m, e, pk, None)
        stone = {k: v for k, v in parts.items() if k == mat}
        self.assertTrue(stone, f"no {mat} faces below the floor line; found {list(parts)}")
        for k in parts:                                    # nothing below the floor line may be the wall finish (plaster/plank)
            self.assertIn(k, (mat, "mat_trim", "mat_door_wood", "mat_glass"), f"foundation face with material {k}")
        F, z0, zf = stone[mat]
        self.assertLess(m.V[F][:, :, 2].min(), z0 + 1e-3)   # reaches the skirt depth
        self.assertGreater(float(np.ptp(m.UV[F].reshape(-1, 2), axis=0).max()), 0.05)   # UVs present and varying (world feet)

    def test_styled_follows_plinth(self):
        n = 0
        for pid, p in bs.load_presets().items():
            if not p.get("plinth"):
                continue
            e, m, _ = tbs.build(pid)
            self._check(e, m, e["_style"]["plinth_mat"])
            n += 1
        self.assertGreater(n, 3)

    def test_unstyled_fieldstone(self):
        pk = tbs.pack()
        e = bsp.sample_entity(pk, next(iter(bs.load_presets())), pk.list("buildings")[0])
        e.pop("style", None)
        e["id"] = "found_plain"
        m, _ = wd.build_building_detailed(wm.Ctx(pk), e)
        self._check(e, m, "mat_wall_stone")

    def test_single_skin_builder(self):
        pk = tbs.pack()
        e = bsp.sample_entity(pk, next(iter(bs.load_presets())), pk.list("buildings")[0])
        e.pop("style", None)
        m = wm.build_building(wm.Ctx(pk), e)
        self._check(e, m, "mat_wall_stone")

    def test_under_door_is_stone(self):
        pk = tbs.pack()
        e = bsp.sample_entity(pk, next(iter(bs.load_presets())), pk.list("buildings")[0])
        e.pop("style", None)
        m, _ = wd.build_building_detailed(wm.Ctx(pk), e)
        d = e["openings"]["doors"][0]["point"]
        c = wm.Ctx(pk).B(d[0], d[1])  # metres already
        F = m.subs["mat_wall_stone"]
        zf = (e["base_elevation_ft"] - pk.frame.z_origin_ft) * FT
        V = m.V[F]
        near = np.any(np.hypot(V[:, :, 0] - c[0], V[:, :, 1] - c[1]) < 2.5 * FT, axis=1) & np.all(V[:, :, 2] <= zf + 1e-4, axis=1)
        self.assertTrue(near.any(), "no stone foundation under the door")

    def test_all_four_sides(self):
        """Every footprint edge has stone foundation faces facing outward, reaching the skirt depth, with UVs; corners are closed (no gaps)."""
        pk = tbs.pack()
        e = bsp.sample_entity(pk, next(iter(bs.load_presets())), pk.list("buildings")[0])
        e.pop("style", None)
        cx = wm.Ctx(pk)
        m, _ = wd.build_building_detailed(cx, e)
        P = [cx.B(p[0], p[1]) for p in e["polygon"]]
        zf = (e["base_elevation_ft"] - pk.frame.z_origin_ft) * FT
        z0 = zf - e["skirt_depth_ft"] * FT
        F = m.subs["mat_wall_stone"]
        V = m.V[F]
        for i in range(len(P)):
            a, b = np.array(P[i]), np.array(P[(i + 1) % len(P)])
            L = np.linalg.norm(b - a)
            u = (b - a) / L
            along = (V[:, :, 0] - a[0]) * u[0] + (V[:, :, 1] - a[1]) * u[1]
            off = np.abs((V[:, :, 0] - a[0]) * -u[1] + (V[:, :, 1] - a[1]) * u[0])
            sel = np.all(off < 1e-3, axis=1) & np.all(V[:, :, 2] <= zf + 1e-4, axis=1)
            self.assertTrue(sel.any(), f"edge {i}: no stone skirt")
            self.assertAlmostEqual(float(along[sel].min()), 0.0, delta=0.05 * FT)       # covers the edge end to end (corner to corner)
            self.assertAlmostEqual(float(along[sel].max()), L, delta=0.05 * FT)
            self.assertAlmostEqual(float(V[sel][:, :, 2].min()), z0, delta=1e-3)
            self.assertGreater(float(np.ptp(m.UV[F[sel]].reshape(-1, 2), axis=0).max()), 0.05)


if __name__ == "__main__":
    unittest.main()
