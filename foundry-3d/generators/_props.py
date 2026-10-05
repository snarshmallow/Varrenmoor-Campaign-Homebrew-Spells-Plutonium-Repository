"""Shared materials and props for the Ossuary Exchange interiors (shops, workshops, warehouse, shafts). Imported by generators.

Floor top is F = 0.1 everywhere. All props are axis-aligned boxes/cylinders/lathe shapes so they merge into a few draw calls, and
faces never share a plane (z-fighting rule): decals/rims/frames are offset 1-2 cm.
"""
import math

import bmesh
import bpy

from _parts import BOTTLE_PROFILES, Skulls, Walls, bm_to_obj, flame_tongue, lathe

F = 0.1


def materials(k):
    return dict(
        ashlar=k.tex("ashlar", "ancient_irregular_ossuary_ashlar", tile=1.6, rough=0.9),
        plaster=k.tex("plaster", "calcified_ancient_lime_and_bone_mortar", tile=1.5, rough=0.95),
        paving=k.tex("paving", "exchange_worn_flagstone_paving", tile=2.4, rough=0.85),
        floor_oak=k.tex("floor_oak", "archive_oak", tile=1.4, rough=0.7),
        oak=k.tex("oak", "archive_oak", tile=1.0, rough=0.7),
        doak=k.tex("dark_oak", "dark_antique_oak", tile=1.0, rough=0.65),
        coak=k.tex("charred", "charred_oak_reinforced_with_bone_straps", tile=1.2, rough=0.8),
        granite=k.tex("granite", "ossuary_gold_flecked_charcoal_granite", tile=1.2, rough=0.4),
        slate=k.tex("slate", "hand_cut_charcoal_ossuary_slate", tile=1.0, rough=0.85),
        brass=k.tex("brass", "tarnished_antique_brass", tile=0.6, rough=0.4, metal=0.4),
        iron=k.tex("iron", "aged_wrought_iron", tile=0.6, rough=0.6, metal=0.3),
        bone=k.tex("bone", "weathered_structural_bone", tile=0.6, rough=0.6),
        dbone=k.tex("dry_bone", "dry_indexed_bone", tile=0.6, rough=0.6),
        soot=k.mat("soot", (0.02, 0.02, 0.02), roughness=1.0),
        teeth=k.mat("skull_teeth", (0.88, 0.84, 0.72), roughness=0.55),
        red=k.mat("red", (0.32, 0.05, 0.05), roughness=0.95),
        navy=k.mat("navy", (0.06, 0.09, 0.22), roughness=0.95),
        green=k.mat("green", (0.05, 0.20, 0.12), roughness=0.95),
        plum=k.mat("plum", (0.22, 0.07, 0.25), roughness=0.95),
        linen=k.mat("linen", (0.58, 0.54, 0.44), roughness=0.95),
        paper=k.mat("paper", (0.62, 0.58, 0.45), roughness=0.9),
        chalk=k.mat("chalk", (0.85, 0.85, 0.8), roughness=1.0),
        board=k.mat("board", (0.06, 0.08, 0.07), roughness=0.95),
        water=k.mat("water", (0.04, 0.12, 0.2), roughness=0.1),
        glass_g=k.mat("bottle_green", (0.08, 0.22, 0.12), roughness=0.2),
        glass_a=k.mat("bottle_amber", (0.40, 0.18, 0.04), roughness=0.2),
        glass_b=k.mat("bottle_blue", (0.06, 0.12, 0.28), roughness=0.2),
        clay=k.mat("clay_jug", (0.30, 0.17, 0.09), roughness=0.8),
        vial_c=k.mat("vial_cyan", (0.1, 0.7, 0.8), roughness=0.2, emission=(0.1, 0.7, 0.8)),
        vial_p=k.mat("vial_purple", (0.5, 0.15, 0.8), roughness=0.2, emission=(0.5, 0.15, 0.8)),
        vial_g=k.mat("vial_green", (0.2, 0.8, 0.25), roughness=0.2, emission=(0.2, 0.8, 0.25)),
        ember=k.mat("ember", (1.0, 0.30, 0.06), roughness=0.7, emission=(1.0, 0.35, 0.08)),
        flame=k.mat("flame", (1.0, 0.12, 0.0), roughness=0.5, emission=(1.0, 0.12, 0.0)),
        flame_core=k.mat("flame_core", (1.0, 0.65, 0.12), roughness=0.5, emission=(1.0, 0.65, 0.12)),
        hot=k.mat("hot_iron", (1.0, 0.25, 0.04), roughness=0.5, emission=(1.0, 0.25, 0.04)),
        candle=k.mat("candle", (0.95, 0.85, 0.6), roughness=0.5, emission=(1.0, 0.65, 0.25)),
        plaque=k.mat("plaque", (0.7, 0.55, 0.2), roughness=0.4, emission=(0.9, 0.6, 0.15)),
        fungus=k.mat("fungus", (0.15, 0.4, 0.25), roughness=0.8, emission=(0.1, 0.5, 0.2)),
        rune=k.mat("rune_glow", (0.2, 0.6, 1.0), roughness=0.4, emission=(0.2, 0.6, 1.0)),
    )


class Shop:
    """Bundles the kit, materials and a Walls helper, and the prop methods."""

    def __init__(self, k):
        self.k = k
        self.M = materials(k)
        self.W = Walls(k, self.M["plaster"], self.M["doak"], self.M["iron"])
        self.B = self.W.B
        self.skulls = Skulls()
        self._glass = {}

    # ---------------------------------------------------------------- basics
    def door(self, door_id, axis, wall_pos, c, swing, w=1.0, h=2.2, hinge_low=True):
        k, F_ = self.k, F
        lw = w - 0.02
        if axis == "x":
            hinge = (c - w / 2 + 0.01, wall_pos, F_) if hinge_low else (c + w / 2 - 0.01, wall_pos, F_)
            yaw = 0 if hinge_low else 180
        else:
            hinge = (wall_pos, c - w / 2 + 0.01, F_) if hinge_low else (wall_pos, c + w / 2 - 0.01, F_)
            yaw = 90 if hinge_low else -90
        return k.door(lw, h - 0.05, hinge=hinge, yaw_deg=yaw, swing=swing, leaf_mat=self.M["coak"], trim_mat=self.M["iron"], door_id=door_id)

    def crate(self, x, y, s=0.6, z=F, mat=None):
        self.B(x - s / 2, x + s / 2, y - s / 2, y + s / 2, z, z + s, mat or self.M["coak"], "crate", 0.02)
        self.B(x - s / 2 - 0.01, x + s / 2 + 0.01, y - 0.03, y + 0.03, z + s * 0.45, z + s * 0.55, self.M["iron"], "crate_band")
        return z + s

    def barrel(self, x, y, r=0.32, h=0.85, z=F, mat=None):
        self.k.cylinder(r, h, loc=(x, y, z + h / 2), material=mat or self.M["oak"], name="barrel", verts=14)
        for f in (0.2, 0.8):
            self.k.cylinder(r + 0.015, 0.05, loc=(x, y, z + h * f), material=self.M["iron"], name="hoop", verts=14)

    def table(self, x0, x1, y0, y1, h=0.8, mat=None, z=F):
        self.B(x0, x1, y0, y1, z + h, z + h + 0.06, mat or self.M["oak"], "table_top", 0.01)
        for lx in (x0 + 0.08, x1 - 0.08):
            for ly in (y0 + 0.08, y1 - 0.08):
                self.B(lx - 0.04, lx + 0.04, ly - 0.04, ly + 0.04, z, z + h, self.M["doak"], "table_leg")

    def stool(self, x, y, h=0.5):
        self.k.cylinder(0.2, 0.05, loc=(x, y, F + h), material=self.M["doak"], name="stool_seat", verts=10)
        for a in (0, 120, 240):
            r = math.radians(a)
            self.k.cylinder(0.025, h, loc=(x + 0.12 * math.cos(r), y + 0.12 * math.sin(r), F + h / 2), material=self.M["doak"], name="stool_leg", verts=6)

    def bench(self, x0, x1, y0, y1, h=0.45):
        self.B(x0, x1, y0, y1, F + h, F + h + 0.05, self.M["oak"], "bench", 0.01)
        for lx in (x0 + 0.1, x1 - 0.1):
            self.B(lx - 0.04, lx + 0.04, y0 + 0.03, y1 - 0.03, F, F + h, self.M["doak"], "bench_leg")

    def chair(self, x, y, face="s"):
        self.B(x - 0.2, x + 0.2, y - 0.2, y + 0.2, F + 0.42, F + 0.47, self.M["oak"], "chair_seat", 0.01)
        by = {"s": (y - 0.2, y - 0.15), "n": (y + 0.15, y + 0.2)}.get(face, (y + 0.15, y + 0.2))
        self.B(x - 0.2, x + 0.2, by[0], by[1], F + 0.47, F + 0.95, self.M["oak"], "chair_back", 0.01)
        for lx in (-0.17, 0.17):
            for ly in (-0.17, 0.17):
                self.B(x + lx - 0.025, x + lx + 0.025, y + ly - 0.025, y + ly + 0.025, F, F + 0.42, self.M["doak"], "chair_leg")

    def rug(self, x0, x1, y0, y1, base=None, edge=None):
        base = base or self.M["red"]
        edge = edge or self.M["plaque"]
        b = 0.1
        self.B(x0, x1, y0, y1, F, F + 0.012, base, "rug")
        for (a0, a1, b0, b1) in ((x0 + b, x1 - b, y0 + b, y0 + b + 0.04), (x0 + b, x1 - b, y1 - b - 0.04, y1 - b),
                                 (x0 + b, x0 + b + 0.04, y0 + b + 0.04, y1 - b - 0.04), (x1 - b - 0.04, x1 - b, y0 + b + 0.04, y1 - b - 0.04)):
            self.B(a0, a1, b0, b1, F + 0.012, F + 0.018, self.M["linen"], "rug_border")

    # ---------------------------------------------------------------- glass (merged per colour)
    def jar(self, x, y, z, kind=0, color="glass_g", scale=1.0):
        key = color
        bm = self._glass.setdefault(key, bmesh.new())
        H, prof = BOTTLE_PROFILES[kind % 3]
        lathe(bm, [(r * scale, f * H * scale) for r, f in prof], x, y, z, seg=7)

    def flush_glass(self):
        for color, bm in self._glass.items():
            bm_to_obj(bm, "glassware", self.M[color])
        self._glass = {}

    # ---------------------------------------------------------------- shelving
    def shelf_unit(self, x0, x1, y0, y1, h, face, rows=4, items="jars", colors=("glass_g", "glass_a", "glass_b", "clay")):
        """Open shelving: the long side facing `face` carries `rows` of items. face in 'n','s','e','w'."""
        M, B = self.M, self.B
        B(x0, x1, y0, y1, F, F + h, M["doak"], "shelf_unit", 0.01)
        horiz = face in "ns"
        span = (x1 - x0) if horiz else (y1 - y0)
        ofs = 0.0
        for r in range(rows):
            z = F + 0.3 + r * ((h - 0.5) / rows)
            n = int(span / 0.34)
            for i in range(n):
                p = (x0 if horiz else y0) + 0.2 + i * ((span - 0.3) / max(n, 1))
                if face == "s":
                    pos = (p, y0 - 0.1)
                elif face == "n":
                    pos = (p, y1 + 0.1)
                elif face == "e":
                    pos = (x1 + 0.1, p)
                else:
                    pos = (x0 - 0.1, p)
                if items == "jars":
                    self.jar(pos[0], pos[1], z, (i + r) % 3, colors[(i * 2 + r) % len(colors)])
                elif items == "vials":
                    self.jar(pos[0], pos[1], z, 2, ("vial_c", "vial_p", "vial_g")[(i + r) % 3], 0.8)
                elif items == "bones":
                    self.B(pos[0] - 0.09, pos[0] + 0.09, pos[1] - 0.05, pos[1] + 0.05, z, z + 0.12 + 0.05 * ((i + r) % 3), M["bone"], "bone_item")
                elif items == "books":
                    mm = (M["red"], M["navy"], M["green"], M["plum"])[(i + r) % 4]
                    self.B(pos[0] - 0.05, pos[0] + 0.05, pos[1] - 0.09, pos[1] + 0.09, z, z + 0.22 + 0.05 * ((i * 3 + r) % 3), mm, "book") if horiz else \
                        self.B(pos[0] - 0.09, pos[0] + 0.09, pos[1] - 0.05, pos[1] + 0.05, z, z + 0.22 + 0.05 * ((i * 3 + r) % 3), mm, "book")
                elif items == "boxes":
                    self.B(pos[0] - 0.12, pos[0] + 0.12, pos[1] - 0.1, pos[1] + 0.1, z, z + 0.18, M["coak"], "box")
            plank = (x0, x1, y1, y1 + 0.22) if face == "n" else (x0, x1, y0 - 0.22, y0) if face == "s" else (x1, x1 + 0.22, y0, y1) if face == "e" else (x0 - 0.22, x0, y0, y1)
            B(plank[0], plank[1], plank[2], plank[3], z - 0.04, z, M["oak"], "shelf_board")

    def cabinet(self, x0, x1, y0, y1, h=1.9, face="s"):
        B, M = self.B, self.M
        B(x0, x1, y0, y1, F, F + h, M["doak"], "cabinet", 0.01)
        B(x0 - 0.03, x1 + 0.03, y0 - 0.03, y1 + 0.03, F + h, F + h + 0.05, M["oak"], "cabinet_top")
        horiz = face in "ns"
        n = max(2, int(((x1 - x0) if horiz else (y1 - y0)) / 0.5))
        for i in range(n):
            for r in range(4):
                z0 = F + 0.1 + r * (h - 0.2) / 4
                p0 = ((x0 if horiz else y0)) + 0.04 + i * (((x1 - x0) if horiz else (y1 - y0)) - 0.08) / n
                p1 = p0 + (((x1 - x0) if horiz else (y1 - y0)) - 0.08) / n - 0.03
                if face == "s":
                    B(p0, p1, y0 - 0.02, y0, z0, z0 + (h - 0.2) / 4 - 0.03, M["oak"], "drawer_front")
                    B((p0 + p1) / 2 - 0.04, (p0 + p1) / 2 + 0.04, y0 - 0.04, y0 - 0.02, z0 + 0.1, z0 + 0.13, M["brass"], "drawer_pull")
                elif face == "n":
                    B(p0, p1, y1, y1 + 0.02, z0, z0 + (h - 0.2) / 4 - 0.03, M["oak"], "drawer_front")
                    B((p0 + p1) / 2 - 0.04, (p0 + p1) / 2 + 0.04, y1 + 0.02, y1 + 0.04, z0 + 0.1, z0 + 0.13, M["brass"], "drawer_pull")
                elif face == "e":
                    B(x1, x1 + 0.02, p0, p1, z0, z0 + (h - 0.2) / 4 - 0.03, M["oak"], "drawer_front")
                    B(x1 + 0.02, x1 + 0.04, (p0 + p1) / 2 - 0.04, (p0 + p1) / 2 + 0.04, z0 + 0.1, z0 + 0.13, M["brass"], "drawer_pull")
                else:
                    B(x0 - 0.02, x0, p0, p1, z0, z0 + (h - 0.2) / 4 - 0.03, M["oak"], "drawer_front")
                    B(x0 - 0.04, x0 - 0.02, (p0 + p1) / 2 - 0.04, (p0 + p1) / 2 + 0.04, z0 + 0.1, z0 + 0.13, M["brass"], "drawer_pull")

    def cage(self, x0, x1, y0, y1, h=0.9, z=F, open_front=None, bars="xy"):
        """Iron-bar cage on a low plinth. open_front: None, or 's'/'n'/'e'/'w' to leave that side's door ajar (gap)."""
        M, B = self.M, self.B
        B(x0, x1, y0, y1, z, z + 0.08, M["doak"], "cage_base", 0.01)
        B(x0 - 0.02, x1 + 0.02, y0 - 0.02, y1 + 0.02, z + h, z + h + 0.05, M["iron"], "cage_top")
        for cx in (x0, x1):
            for cy in (y0, y1):
                B(cx - 0.025, cx + 0.025, cy - 0.025, cy + 0.025, z + 0.08, z + h, M["iron"], "cage_post")
        n = max(2, int((x1 - x0) / 0.12))
        for i in range(1, n):
            xx = x0 + i * (x1 - x0) / n
            if open_front != "s" or i < n // 3 or i > 2 * n // 3:
                B(xx - 0.01, xx + 0.01, y0 - 0.005, y0 + 0.005, z + 0.08, z + h, M["iron"], "bar")
            if open_front != "n":
                B(xx - 0.01, xx + 0.01, y1 - 0.005, y1 + 0.005, z + 0.08, z + h, M["iron"], "bar")
        m = max(2, int((y1 - y0) / 0.12))
        for i in range(1, m):
            yy = y0 + i * (y1 - y0) / m
            B(x0 - 0.005, x0 + 0.005, yy - 0.01, yy + 0.01, z + 0.08, z + h, M["iron"], "bar")
            B(x1 - 0.005, x1 + 0.005, yy - 0.01, yy + 0.01, z + 0.08, z + h, M["iron"], "bar")

    # ---------------------------------------------------------------- lights and fire
    def lantern(self, x, y, z, hang=0.0):
        k = self.k
        k.cylinder(0.06, 0.16, loc=(x, y, z), material=self.M["iron"], name="lantern", verts=8)
        k.sphere(0.06, loc=(x, y, z), material=self.M["candle"], name="lantern_flame", segments=8)
        if hang:
            self.B(x - 0.01, x + 0.01, y - 0.01, y + 0.01, z + 0.09, z + 0.09 + hang, self.M["iron"], "lantern_chain")

    def fire(self, x, y, z, w=1.0):
        """A small fire bed: glowing embers, two logs and flame tongues."""
        M = self.M
        self.B(x - w / 2, x + w / 2, y - 0.3, y + 0.3, z, z + 0.06, M["ember"], "embers")
        for dy in (-0.1, 0.12):
            self.k.cylinder(0.08, w * 0.8, loc=(x, y + dy, z + 0.12), rot=(0, 90, 6 * dy * 10), material=M["coak"], name="log", verts=8)
        for i, fx in enumerate((-0.3, -0.1, 0.12, 0.32)):
            fh = (0.45, 0.65, 0.55, 0.4)[i] * w
            flame_tongue(x + fx * w, y + (0.05 if i % 2 else -0.05), z + 0.05, fh, 0.12 * w, (0.06 if i % 2 else -0.07), M["flame"], "flame")
            flame_tongue(x + fx * w, y + (0.05 if i % 2 else -0.05), z + 0.05, fh * 0.6, 0.07 * w, (0.04 if i % 2 else -0.04), M["flame_core"], "flame_core")

    def finish(self, name="skulls"):
        self.skulls.finish(self.M["bone"], self.M["soot"], self.M["teeth"], name=name)
        self.flush_glass()
