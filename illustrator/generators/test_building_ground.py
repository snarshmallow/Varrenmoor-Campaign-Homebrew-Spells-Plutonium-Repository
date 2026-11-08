"""Tests for building_ground.py (python test_building_ground.py): a building on a 25 % slope, a flat site and a ridge never has terrain burying its walls /
door sill / eaves, never floats beyond the cap, and the skirt reaches below the lowest ground. Uses the real terrain_heights (pads) + the mesh sampler."""
import math
import os
import sys
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import building_ground as bg  # noqa: E402
import building_ground_audit as ba  # noqa: E402
import road_grade as rg  # noqa: E402
import worldpack as wp  # noqa: E402
import worldpack_mesh as wm  # noqa: E402

CELL, ZO = 2.5, 80.0
N = 80
CX, CY = 100.0, 100.0


def ground(kind):
    Y, X = np.mgrid[0:N, 0:N] * CELL
    if kind == "flat":
        z = np.full((N, N), 100.0)
    elif kind == "slope":                      # 25 % rising to the east
        z = 100.0 + 0.25 * (X - CX)
    elif kind == "steep":                      # 60 % rising to the east (more than the caps can follow)
        z = 100.0 + 0.6 * (X - CX)
    elif kind == "ridge":                      # a ridge running north-south through the building
        z = 100.0 + 5.0 * np.exp(-((X - CX) / 6.0) ** 2)
    else:                                      # cross slope with a bumpy door side
        z = 100.0 + 0.25 * (Y - CY) + 0.8 * np.sin(X / 3.0)
    return z.astype(np.float32)


def building(h, w=16.0, d=12.0, door_side=-1):
    """Rectangular house centred on (CX, CY) with one door on the west (door_side -1) or east wall; base from building_ground.resolve like the exporter."""
    poly = [[CX - w / 2, CY - d / 2], [CX + w / 2, CY - d / 2], [CX + w / 2, CY + d / 2], [CX - w / 2, CY + d / 2]]
    dx = CX + door_side * w / 2
    doors = [{"id": "d1", "point": [dx, CY], "facing": [float(door_side), 0.0], "width_ft": 3.5}]
    base0 = float(rg.mesh_height(h, CELL, CX, CY))                    # what a naive generator picks: the centre sample
    base, skirt, rep = bg.resolve(poly, doors, base0, h, CELL)
    return {"id": "b1", "polygon": poly, "base_elevation_ft": base, "skirt_depth_ft": skirt, "wall_height_ft": 10.0, "floors": 1,
            "roof": {"type": "gable", "ridge_height_ft": 3.5, "overhang_ft": 1.5}, "obb": {"center": [CX, CY], "angle_deg": 0.0, "length_ft": w, "width_ft": d},
            "openings": {"doors": doors}}, rep


def site(kind, **kw):
    h = ground(kind)
    e, rep = building(h, **kw)
    pk = types.SimpleNamespace(heights=h, cell_ft=CELL, place="synthetic", entities={"buildings": [e], "roads": [], "bridges": []})
    pk.list = lambda t=None: pk.entities.get(t, [])
    pk.frame = wp.Frame(N * CELL, N * CELL, ZO)
    hf = wm.terrain_heights(pk)[0]
    return e, h, hf, rep


class BuildingGround(unittest.TestCase):
    def check(self, kind, max_gap=1.5, **kw):
        e, h0, hf, rep = site(kind, **kw)
        r = ba.audit_building(e, hf, CELL, rg)
        self.assertLessEqual(r["wall_burial_ft"], 0.02, f"{kind}: ground above the floor line along the walls")
        self.assertLessEqual(r["interior_burial_ft"], 0.02, f"{kind}: ground above the floor under the footprint")
        self.assertGreaterEqual(r["min_door_clear_ft"], bg.DEFAULTS["sill_ft"] - 0.01, f"{kind}: door sill must clear the ground at the door and 2 ft in front")
        self.assertLessEqual(r["skirt_short_ft"], 0.01, f"{kind}: daylight under the wall (skirt too shallow)")
        self.assertLessEqual(r["wall_gap_ft"], max_gap, f"{kind}: wall floats {r['wall_gap_ft']} ft above the ground")
        self.assertGreaterEqual(bg.eave_clearance(e, hf, CELL), bg.DEFAULTS["min_eave_ft"], f"{kind}: eave too close to the ground")
        return e, r, rep

    def test_flat(self):
        e, r, rep = self.check("flat")
        self.assertFalse(rep["changed"])

    def test_slope_25_percent(self):
        e, r, rep = self.check("slope")
        self.assertLessEqual(r["wall_gap_ft"], bg.DEFAULTS["max_float_ft"] + 0.05)
        self.assertGreater(e["skirt_depth_ft"], r["wall_gap_ft"])      # skirt covers the whole downhill gap

    def test_ridge(self):
        self.check("ridge")

    def test_cross_slope_door_on_the_east(self):
        self.check("cross", door_side=1)

    def test_steep_slope_still_buries_nothing(self):
        e, r, rep = self.check("steep", max_gap=3.0)
        self.assertTrue(rep["changed"])

    def test_base_follows_footprint_not_centre(self):
        """On a 25 % slope the centre sample is NOT the base when that would float a wall: the base stays within the float cap of the lowest wall ground."""
        e, h0, hf, rep = site("slope")
        lo = min(rg.mesh_height(h0, CELL, x, y) for x, y in e["polygon"])
        self.assertLessEqual(e["base_elevation_ft"], lo + bg.DEFAULTS["max_float_ft"] + 1e-3)

    def test_pad_only_cuts(self):
        e, h0, hf, rep = site("slope")
        self.assertLessEqual(float((hf - h0).max()), 1e-4)

    def test_pad_leaves_far_ground_alone(self):
        e, h0, hf, rep = site("slope")
        self.assertEqual(float(np.abs(hf[:, :8] - h0[:, :8]).max()), 0.0)


class DyersWalkPack(unittest.TestCase):
    def test_pack_has_no_buried_building(self):
        import bridge_maker as bm
        d = os.path.join(bm.WORLD, "bridgehollow__dyers_walk_local", "export")
        if not os.path.isdir(d):
            self.skipTest("no Dyers Walk pack")
        pk = wp.load_pack(d)
        rows = ba.audit(pk, with_mesh=False)
        self.assertLessEqual(max(r["wall_burial_ft"] for r in rows), 0.05)
        self.assertGreaterEqual(min(r["min_door_clear_ft"] for r in rows if r["min_door_clear_ft"] is not None), 0.1)


if __name__ == "__main__":
    unittest.main()
