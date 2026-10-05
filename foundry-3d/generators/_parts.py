"""Shared low-poly parts for the Ossuary Exchange generators (imported by generators; not built on its own).
Everything here builds into bmesh and is merged per material, so hundreds of bottles/skulls stay a few draw calls.
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector


def lathe(bm, profile, cx, cy, cz, seg=8, sway=(0.0, 0.0)):
    """Spin a (radius, height) profile around Z into bm: closed flat base, pointed tip when the last radius is 0.
    `sway` shifts the ring centres in an S-curve so flames can lean and curl."""
    top = profile[-1][1] or 1.0
    rings = []
    for r, h in profile:
        t = h / top
        ox, oy = sway[0] * t * math.sin(math.pi * 1.5 * t), sway[1] * t * math.sin(math.pi * 1.5 * t)
        if r <= 1e-6:
            rings.append(bm.verts.new((cx + ox, cy + oy, cz + h)))
        else:
            rings.append([bm.verts.new((cx + ox + r * math.cos(2 * math.pi * i / seg),
                                        cy + oy + r * math.sin(2 * math.pi * i / seg), cz + h)) for i in range(seg)])
    bm.faces.new(rings[0][::-1])
    for j in range(len(rings) - 1):
        a, b = rings[j], rings[j + 1]
        for i in range(seg):
            i2 = (i + 1) % seg
            if isinstance(b, list):
                bm.faces.new((a[i], a[i2], b[i2], b[i]))
            else:
                bm.faces.new((a[i], a[i2], b))
    if isinstance(rings[-1], list):
        bm.faces.new(rings[-1])


def bm_to_obj(bm, name, mats):
    """Turn a bmesh into a linked object; `mats` is one material or a list matching faces' material_index."""
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    for m in (mats if isinstance(mats, (list, tuple)) else [mats]):
        ob.data.materials.append(m)
    return ob


def flame_tongue(x, y, z, height, radius, sway, mat, name):
    """A teardrop flame leaning by `sway` metres at the tip (~50 triangles)."""
    bm = bmesh.new()
    fr = (0.55, 0.9, 1.0, 0.95, 0.8, 0.6, 0.38, 0.18, 0.0)
    ht = (0.0, 0.1, 0.25, 0.4, 0.55, 0.7, 0.82, 0.93, 1.0)
    lathe(bm, [(radius * a, height * b) for a, b in zip(fr, ht)], x, y, z, seg=6, sway=(sway, sway * 0.5))
    return bm_to_obj(bm, name, mat)


# (height-fraction profiles) wine bottle, squat jug, tall flask: (height m, ((radius, fraction), ...))
BOTTLE_PROFILES = (
    (0.30, ((0.050, 0), (0.050, 0.58), (0.040, 0.66), (0.020, 0.78), (0.020, 0.94), (0.026, 0.97), (0.026, 1.0))),
    (0.22, ((0.062, 0), (0.076, 0.25), (0.076, 0.5), (0.052, 0.72), (0.028, 0.85), (0.032, 1.0))),
    (0.34, ((0.036, 0), (0.036, 0.7), (0.020, 0.82), (0.020, 0.97), (0.026, 1.0))),
)


class Skulls:
    """Collects any number of skulls into one bmesh (3 materials) and emits a single object.

    Local skull space: +Y is the face, +Z up, origin under the jaw, about 1.9 units tall; `s` scales it to metres
    (0.1 gives a 19 cm skull). add() turns the face toward a plan-view target point, e.g. the room centre.
    ~280 triangles each: cranium, maxilla, jaw with rami, two teeth rows, deep eye sockets and a nose cavity."""
    BONE, DARK, TEETH = 0, 1, 2

    def __init__(self):
        self.bm = bmesh.new()

    def _prim(self, kind, m, mat, **kw):
        n0 = len(self.bm.faces)
        if kind == "sphere":
            bmesh.ops.create_uvsphere(self.bm, u_segments=kw.get("u", 10), v_segments=kw.get("v", 7), radius=1.0, matrix=m)
        else:
            bmesh.ops.create_cube(self.bm, size=1.0, matrix=m)
        self.bm.faces.ensure_lookup_table()
        for f in self.bm.faces[n0:]:
            f.material_index = mat

    def add(self, x, y, z, face_to=(0.0, 0.0), s=0.1, tilt_deg=0.0):
        dx, dy = face_to[0] - x, face_to[1] - y
        yaw = math.atan2(-dx, dy)                  # local +Y -> (dx, dy)
        base = Matrix.Translation((x, y, z)) @ Matrix.Rotation(yaw, 4, "Z") @ Matrix.Rotation(math.radians(tilt_deg), 4, "X") @ Matrix.Scale(s, 4)

        def at(px, py, pz, sx, sy, sz):
            return base @ Matrix.Translation((px, py, pz)) @ Matrix.Diagonal((sx, sy, sz, 1.0))

        self._prim("sphere", at(0, 0, 1.05, 0.78, 0.95, 0.85), self.BONE, u=10, v=7)          # cranium
        self._prim("cube", at(0, 0.45, 0.58, 0.95, 0.8, 0.62), self.BONE)                       # face / maxilla
        self._prim("cube", at(0, 0.35, 0.13, 0.82, 0.9, 0.24), self.BONE)                       # jaw
        for sx in (-1, 1):
            self._prim("cube", at(sx * 0.62, -0.15, 0.55, 0.14, 0.26, 0.7), self.BONE)           # jaw rami
            self._prim("sphere", at(sx * 0.36, 0.80, 1.0, 0.25, 0.11, 0.22), self.DARK, u=8, v=5)  # eye sockets
        self._prim("cube", at(0, 0.82, 0.33, 0.7, 0.1, 0.14), self.TEETH)                       # upper teeth
        self._prim("cube", at(0, 0.78, 0.20, 0.64, 0.1, 0.12), self.TEETH)                      # lower teeth
        self._prim("cube", at(0, 0.88, 0.7, 0.13, 0.07, 0.2), self.DARK)                        # nose cavity

    def finish(self, bone, dark, teeth, name="skulls"):
        return bm_to_obj(self.bm, name, [bone, dark, teeth])
