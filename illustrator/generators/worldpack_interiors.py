"""3D interiors for world pack buildings that carry a generated `layout` (see interiors.py): floors, upper-storey slabs with stair holes, ceilings with
joists, partition walls with door openings, straight stairs, interior door leaves (separate hinge nodes, isDoor), low-poly furniture props, light hints.

Hooks (small, all guarded by `e.get("layout")`):
  worldpack_mesh.build_parts       -> add_interior(cx, e, mesh, door_nodes) after build_building_detailed
  worldpack_detail.build_building_detailed -> apply_layout_windows(...) so the exterior windows are the layout's windows
  worldpack_split._entry           -> part["layered_nodes"] replace the single building node; part["interior_lights"] -> placements.json "lights"

glTF nodes per building (names; extras carry `tags`, `storey`, `building`):
  <id>                 exterior shell of the ground storey + foundation        tags [building, shell]   storey 0
  <id>_shell_f<s>      exterior walls of storey s >= 1 (windows, trim)         tags [building, shell]   storey s
  <id>_int_f<s>        floor (s=0) or slab+ceiling+joists below it, partitions, stairs of storey s    tags [interior]  storey s
  <id>_roof            roof, gables, top ceiling plate + beams                 tags [building, roof]
  <id>_props_f<s>      furniture of storey s (hide with tag `prop`)            tags [interior, prop]    storey s
  <id>_idoor_f<s>_<n>  interior door leaves, origin on the hinge               isDoor, doorStyle 1, doorAnimateAngle 1.5708 (RADIANS, read raw by 3D Canvas)
Toggle `_roof`, then `_shell_f<n>` / `_int_f<n>` / `_props_f<n>` from the top storey down for a cutaway.
"""
import math

import numpy as np

import worldpack_mesh as wm

FT = wm.FT
Builder, Mesh = wm.Builder, wm.Mesh
SLAB, PART_T, DOOR_H, STOREY = 0.6, 0.4, 6.8, 10.0
PLATE_DROP, PLATE_T = 0.7, 0.2
INTERIOR_MATS = {"mat_furn_wood": ("#7b5a3a", 0.85, None), "mat_fabric": ("#8a3b3b", 0.95, None), "mat_straw": ("#c9b36a", 1.0, None),
                 "mat_hearth_stone": ("#6e6a64", 0.95, None), "mat_ember": ("#e0701c", 0.7, None), "mat_joist": ("#5b4129", 0.9, None),
                 "mat_ceiling": ("#bfae8e", 0.95, None),
                 # interior styles (interior_styles.py): flat colours for small props, textured ones come from worldpack_pbr.CATALOG
                 "mat_pottery": ("#a9683f", 0.8, None), "mat_herb": ("#6f7f3f", 1.0, None), "mat_linen": ("#d9d2bd", 0.95, None),
                 "mat_int_plank": ("#64492e", 0.85, None), "mat_int_flag": ("#8a867c", 0.82, None), "mat_int_earth": ("#6e5a3c", 0.97, None),
                 "mat_int_lime": ("#e0d8c2", 0.95, None), "mat_int_frame": ("#d8cdb4", 0.9, None), "mat_int_stone": ("#7a756c", 0.85, None),
                 "mat_int_boards": ("#6b4e30", 0.88, None), "mat_int_slab": ("#8a867c", 0.78, None), "mat_int_rug": ("#8a5a3c", 0.98, None)}


def _cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


class _G:
    """Mesh builder with outward-oriented faces (winding fixed from a hint vector)."""

    def __init__(self, world=None):
        """world: None = legacy per-axis UVs (4 ft repeat); (zf_m, uv_offset) = constant texel density per material tile size, rails on the floor line (styled interiors)."""
        self.b = Builder()
        self.world = world

    def _tile(self, mat, tile):
        if self.world is None:
            return tile
        import worldpack_pbr as pbr
        return pbr.tile_ft(mat, 4.0)

    def fout(self, mat, pts, hint, tile=4.0):
        p0, p1, p2 = (np.array(p, float) for p in pts[:3])
        n = np.cross(p1 - p0, p2 - p0)
        if np.dot(n, hint) < 0:
            pts = pts[::-1]
            n = -n
        if self.world is not None:
            self.b.face(mat, [tuple(p) for p in pts], wm.world_uv(pts, self._tile(mat, tile), self.world[1], self.world[0]))
            return
        ax = int(np.argmax(np.abs(n)))
        t = tile * FT
        uvs = []
        for p in pts:
            x, y, z = p
            uvs.append(((x, y), (y, z), (x, z))[ax])
        self.b.face(mat, [tuple(p) for p in pts], [(u / t, -v / t) for u, v in uvs])

    def horiz(self, mat, ring, z, up=True, tile=4.0):
        """Horizontal polygon (Blender xy ring) at height z, facing up or down."""
        tris = wm.earclip(ring)
        tile = self._tile(mat, tile)
        o = self.world[1] if self.world is not None else (0.0, 0.0)
        ids = [self.b.vert((p[0], p[1], z), (p[0] / FT / tile + o[0], -p[1] / FT / tile + o[1])) for p in ring]
        for a, b, c in tris:
            self.b.tri(mat, ids[a], ids[b], ids[c]) if up else self.b.tri(mat, ids[a], ids[c], ids[b])

    def box(self, mat, T, x0, x1, y0, y1, z0, z1, skip=()):
        """Box in a local frame; T(lx, ly) -> Blender (x, y). z absolute. skip: face names among x0 x1 y0 y1 z0 z1."""
        c = lambda x, y, z: (*T(x, y), z)
        ctr = np.array([*T((x0 + x1) / 2, (y0 + y1) / 2), (z0 + z1) / 2])
        F = {"x0": [c(x0, y0, z0), c(x0, y1, z0), c(x0, y1, z1), c(x0, y0, z1)], "x1": [c(x1, y0, z0), c(x1, y1, z0), c(x1, y1, z1), c(x1, y0, z1)],
             "y0": [c(x0, y0, z0), c(x1, y0, z0), c(x1, y0, z1), c(x0, y0, z1)], "y1": [c(x0, y1, z0), c(x1, y1, z0), c(x1, y1, z1), c(x0, y1, z1)],
             "z0": [c(x0, y0, z0), c(x1, y0, z0), c(x1, y1, z0), c(x0, y1, z0)], "z1": [c(x0, y0, z1), c(x1, y0, z1), c(x1, y1, z1), c(x0, y1, z1)]}
        for k, pts in F.items():
            if k in skip:
                continue
            fc = np.mean(np.array(pts), axis=0)
            self.fout(mat, pts, fc - ctr)

    def prism(self, mat, T, cx, cy, r, z0, z1, n=8):
        ring = [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
        ctr = np.array([*T(cx, cy), (z0 + z1) / 2])
        for k in range(n):
            a, b = ring[k], ring[(k + 1) % n]
            pts = [(*T(*a), z0), (*T(*b), z0), (*T(*b), z1), (*T(*a), z1)]
            self.fout(mat, pts, np.mean(np.array(pts), axis=0) - ctr)
        for z, up in ((z1, True), (z0, False)):
            pts = [(*T(*p), z) for p in ring]
            self.fout(mat, pts, np.array([0, 0, 1.0 if up else -1.0]))

    def build(self):
        return self.b.build()


def _band_split(mesh, zs):
    """Split a mesh at the horizontal planes zs (metres, ascending) -> list of len(zs)+1 meshes (triangles are cut where they cross)."""
    edges = [-1e9] + list(zs) + [1e9]

    def clip(poly, plane, keep_above):
        res = []
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            ina = (a[0][2] >= plane) if keep_above else (a[0][2] <= plane)
            inb = (b[0][2] >= plane) if keep_above else (b[0][2] <= plane)
            if ina:
                res.append(a)
            if ina != inb:
                t = (plane - a[0][2]) / (b[0][2] - a[0][2])
                res.append((tuple(a[0][k] + t * (b[0][k] - a[0][k]) for k in range(3)), tuple(a[1][k] + t * (b[1][k] - a[1][k]) for k in range(2))))
        return res
    outs = []
    for bi in range(len(edges) - 1):
        lo, hi = edges[bi], edges[bi + 1]
        V, UV, subs = [], [], {}
        for mat, F in mesh.subs.items():
            for f in F:
                poly = [(tuple(mesh.V[i]), tuple(mesh.UV[i])) for i in f]
                zmin, zmax = min(p[0][2] for p in poly), max(p[0][2] for p in poly)
                if zmax - zmin < 1e-9:
                    if not (lo <= zmin < hi):
                        continue
                else:
                    if zmax <= lo + 1e-9 or zmin >= hi - 1e-9:
                        continue
                    if lo > -1e8:
                        poly = clip(poly, lo, True)
                    if hi < 1e8 and len(poly) >= 3:
                        poly = clip(poly, hi, False)
                if len(poly) < 3:
                    continue
                ids = []
                for p, uv in poly:
                    V.append(p)
                    UV.append(uv)
                    ids.append(len(V) - 1)
                for k in range(1, len(ids) - 1):
                    subs.setdefault(mat, []).append((ids[0], ids[k], ids[k + 1]))
        outs.append(Mesh(np.array(V).reshape(-1, 3), np.array(UV).reshape(-1, 2), subs, mesh.smooth))
    return outs


def apply_layout_windows(edge_holes, P, e, cx, zf):
    """Replace the derived windows of worldpack_detail.plan_holes by the layout's windows (ft world points -> edge index + u in metres on the CCW Blender polygon P)."""
    lay = e.get("layout") or {}
    n = len(P)
    out = [[h for h in hs if h["kind"] != "window"] for hs in edge_holes]
    for w in lay.get("windows", []):
        pb = cx.B(w["point"][0], w["point"][1])
        best = None
        for i in range(n):
            a, b = P[i], P[(i + 1) % n]
            L = math.dist(a, b)
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            u = (pb[0] - a[0]) * ux + (pb[1] - a[1]) * uy
            v = -(pb[0] - a[0]) * uy + (pb[1] - a[1]) * ux
            if 0 <= u <= L and (best is None or abs(v) < best[0]):
                best = (abs(v), i, u)
        if best and best[0] < 0.6:
            hw = w["width_ft"] * FT / 2
            z0 = zf + (w["floor"] * STOREY + w["sill_ft"]) * FT
            out[best[1]].append({"u0": best[2] - hw, "u1": best[2] + hw, "z0": z0, "z1": z0 + w["height_ft"] * FT, "kind": "window"})
    return [sorted(hs, key=lambda h: (h["u0"], h["z0"])) for hs in out]


# ------------------------------------------------------------------ furniture
def _fixture(g, T, typ, sx, sy, hz, mat, z0, ceil_z, S=None):
    """Low-poly prop in its local frame (x along the wall, y out from the wall, back at y = -sy/2). z0 = floor level (m).
    S: interior style preset (interior_styles.py) or None / plain for the original props."""
    x0, x1, y0, y1 = -sx / 2 * FT, sx / 2 * FT, -sy / 2 * FT, sy / 2 * FT
    h = hz * FT
    f = lambda v: v * FT
    if S is not None and S["name"] != "plain" and _fixture_styled(g, T, typ, sx, sy, hz, mat, z0, ceil_z, S):
        return
    if typ == "table" or typ == "desk":
        g.box(mat, T, x0, x1, y0, y1, z0 + h - f(0.25), z0 + h)
        for lx in (x0 + f(0.2), x1 - f(0.45)):
            for ly in (y0 + f(0.2), y1 - f(0.45)):
                g.box(mat, T, lx, lx + f(0.25), ly, ly + f(0.25), z0, z0 + h - f(0.25), skip=("z0", "z1"))
    elif typ == "bench":
        g.box(mat, T, x0, x1, y0, y1, z0 + h - f(0.2), z0 + h)
        for lx in (x0 + f(0.3), x1 - f(0.5)):
            g.box(mat, T, lx, lx + f(0.2), y0 + f(0.1), y1 - f(0.1), z0, z0 + h - f(0.2), skip=("z0", "z1"))
    elif typ == "shelf":
        for lx in (x0, x1 - f(0.15)):
            g.box(mat, T, lx, lx + f(0.15), y0, y1, z0, z0 + h)
        for k in range(5):
            zz = z0 + f(0.3) + k * (h - f(0.5)) / 4
            g.box(mat, T, x0 + f(0.15), x1 - f(0.15), y0, y1, zz, zz + f(0.12), skip=("x0", "x1"))
    elif typ == "bed":       # head at the wall (y0)
        g.box("mat_furn_wood", T, x0, x1, y0, y1, z0 + f(0.4), z0 + f(1.0))
        g.box("mat_fabric", T, x0 + f(0.15), x1 - f(0.15), y0 + f(0.15), y1 - f(0.15), z0 + f(1.0), z0 + f(1.45), skip=("z0",))
        g.box("mat_ceiling", T, x0 + f(0.4), x1 - f(0.4), y0 + f(0.25), y0 + f(1.2), z0 + f(1.45), z0 + f(1.7), skip=("z0",))
        g.box("mat_furn_wood", T, x0, x1, y0, y0 + f(0.2), z0 + f(1.0), z0 + f(2.8))
        for lx in (x0, x1 - f(0.3)):
            g.box("mat_furn_wood", T, lx, lx + f(0.3), y1 - f(0.3), y1, z0, z0 + f(0.4), skip=("z0",))
            g.box("mat_furn_wood", T, lx, lx + f(0.3), y0, y0 + f(0.3), z0, z0 + f(0.4), skip=("z0",))
    elif typ == "chest":
        g.box(mat, T, x0, x1, y0, y1, z0, z0 + h * 0.75)
        g.box("mat_joist", T, x0 - f(0.05), x1 + f(0.05), y0 - f(0.05), y1 + f(0.05), z0 + h * 0.75, z0 + h, skip=("z0",))
    elif typ == "barrel":
        g.prism(mat, T, 0.0, 0.0, min(sx, sy) / 2 * FT, z0, z0 + h)
        g.prism("mat_iron", T, 0.0, 0.0, min(sx, sy) / 2 * FT + f(0.04), z0 + h * 0.3, z0 + h * 0.36)
    elif typ in ("crate", "hay"):
        g.box(mat, T, x0, x1, y0, y1, z0, z0 + h)
    elif typ in ("counter", "workbench"):
        g.box(mat, T, x0 - f(0.1), x1 + f(0.1), y0 - f(0.05), y1 + f(0.1), z0 + h - f(0.2), z0 + h)
        g.box("mat_joist", T, x0, x1, y0 + f(0.1), y1 - f(0.1), z0, z0 + h - f(0.2), skip=("z0", "z1"))
    elif typ == "hearth":
        g.box(mat, T, x0, x1, y0, y1, z0, z0 + f(0.3))
        g.box(mat, T, -f(1.7), f(1.7), y0, y0 + f(1.4), z0 + f(0.3), ceil_z, skip=("z0", "z1"))
        g.box("mat_ember", T, -f(0.8), f(0.8), y0 + f(1.38), y0 + f(1.46), z0 + f(0.5), z0 + f(1.7), skip=("z0",))
        g.box("mat_ember", T, -f(0.8), f(0.8), y0 + f(0.1), y0 + f(1.3), z0 + f(0.3), z0 + f(0.5), skip=("z0",))
    else:
        g.box(mat, T, x0, x1, y0, y1, z0, z0 + h)


def _fixture_styled(g, T, typ, sx, sy, hz, mat, z0, ceil_z, S):
    """Style variants of the props; returns True when it drew the prop. Boxes and small prisms only, no coplanar overlaps."""
    x0, x1, y0, y1 = -sx / 2 * FT, sx / 2 * FT, -sy / 2 * FT, sy / 2 * FT
    h = hz * FT
    f = lambda v: v * FT
    M = S["mats"]
    if typ == "table" and S["name"] != "burgher_townhouse":          # trestle table: thick top, two slab ends, stretcher
        g.box(mat, T, x0, x1, y0, y1, z0 + h - f(0.3), z0 + h)
        for lx in (x0 + f(0.4), x1 - f(0.65)):
            g.box(mat, T, lx, lx + f(0.25), y0 + f(0.2), y1 - f(0.2), z0, z0 + h - f(0.3), skip=("z0", "z1"))
        g.box(mat, T, x0 + f(0.65), x1 - f(0.65), -f(0.08), f(0.08), z0 + f(0.5), z0 + f(0.66), skip=("x0", "x1"))
        if S.get("goods"):
            g.prism("mat_pottery", T, -f(0.9), -f(0.1), f(0.38), z0 + h, z0 + h + f(0.2), 6)
            g.prism("mat_pottery", T, f(0.9), f(0.3), f(0.2), z0 + h, z0 + h + f(0.55), 6)
        return True
    if typ == "table" and S.get("goods"):                            # burgher: legged table + a candlestick and a jug
        g.box(mat, T, x0, x1, y0, y1, z0 + h - f(0.25), z0 + h)
        for lx in (x0 + f(0.2), x1 - f(0.45)):
            for ly in (y0 + f(0.2), y1 - f(0.45)):
                g.box(mat, T, lx, lx + f(0.25), ly, ly + f(0.25), z0, z0 + h - f(0.25), skip=("z0", "z1"))
        g.prism("mat_pottery", T, f(0.8), 0.0, f(0.2), z0 + h, z0 + h + f(0.55), 6)
        g.prism("mat_linen", T, -f(0.7), 0.0, f(0.07), z0 + h, z0 + h + f(0.5), 5)
        return True
    if typ == "shelf" and S.get("goods"):                            # the plain shelf plus jars on two boards
        for lx in (x0, x1 - f(0.15)):
            g.box(mat, T, lx, lx + f(0.15), y0, y1, z0, z0 + h)
        for k in range(5):
            zz = z0 + f(0.3) + k * (h - f(0.5)) / 4
            g.box(mat, T, x0 + f(0.15), x1 - f(0.15), y0, y1, zz, zz + f(0.12), skip=("x0", "x1"))
            if k in (1, 3):
                for j, lx in enumerate((x0 + f(0.55), 0.0, x1 - f(0.55))):
                    g.prism("mat_pottery" if (j + k) % 2 else "mat_herb", T, lx, 0.0, f(0.2), zz + f(0.12), zz + f(0.12) + f(0.42 if j != 1 else 0.3), 6)
        return True
    if typ == "chest" and S.get("chest_bands"):                      # iron-strapped chest
        g.box(mat, T, x0, x1, y0, y1, z0, z0 + h * 0.75)
        g.box("mat_joist", T, x0 - f(0.05), x1 + f(0.05), y0 - f(0.05), y1 + f(0.05), z0 + h * 0.75, z0 + h, skip=("z0",))
        for lx in (x0 + f(0.35), x1 - f(0.55)):
            g.box("mat_iron", T, lx, lx + f(0.2), y0 - f(0.09), y1 + f(0.09), z0 + f(0.02), z0 + h + f(0.03), skip=("z0",))
        return True
    if typ == "hearth":                                              # stone chimney breast, mantel beam, a cauldron in the fire
        st = M.get("stone") or mat
        g.box(st, T, x0, x1, y0, y1, z0, z0 + f(0.3))
        g.box(st, T, -f(1.7), f(1.7), y0, y0 + f(1.4), z0 + f(0.3), ceil_z, skip=("z0", "z1"))
        g.box("mat_ember", T, -f(0.8), f(0.8), y0 + f(1.38), y0 + f(1.46), z0 + f(0.5), z0 + f(1.7), skip=("z0",))
        g.box("mat_ember", T, -f(0.8), f(0.8), y0 + f(0.1), y0 + f(1.3), z0 + f(0.3), z0 + f(0.5), skip=("z0",))
        if S.get("mantel"):
            g.box(M["beam"], T, -f(2.1), f(2.1), y0, y0 + f(1.75), z0 + f(4.7), z0 + f(5.2), skip=("y0",))
        g.prism("mat_iron", T, 0.0, y0 + f(0.8), f(0.5), z0 + f(0.5), z0 + f(1.0), 8)
        return True
    if typ == "bed" and S.get("bed") != "frame":
        kind = S["bed"]
        W = "mat_furn_wood"
        if kind == "pallet":                                         # straw tick on the floor, a rag blanket
            g.box("mat_straw", T, x0 + f(0.15), x1 - f(0.15), y0 + f(0.15), y1 - f(0.15), z0, z0 + f(0.55))
            g.box("mat_fabric", T, x0 + f(0.3), x1 - f(0.3), y0 + f(2.2), y1 - f(0.3), z0 + f(0.55), z0 + f(0.65), skip=("z0",))
            return True
        if kind == "straw":                                          # low timber box bed, straw tick, folded blanket, bolster
            g.box(W, T, x0, x1, y0, y1, z0 + f(0.3), z0 + f(0.8))
            g.box("mat_straw", T, x0 + f(0.15), x1 - f(0.15), y0 + f(0.15), y1 - f(0.15), z0 + f(0.8), z0 + f(1.25), skip=("z0",))
            g.box("mat_fabric", T, x0 + f(0.25), x1 - f(0.25), y0 + f(2.4), y1 - f(0.25), z0 + f(1.25), z0 + f(1.4), skip=("z0",))
            g.box("mat_linen", T, x0 + f(0.5), x1 - f(0.5), y0 + f(0.3), y0 + f(1.2), z0 + f(1.25), z0 + f(1.5), skip=("z0",))
            g.box(W, T, x0, x1, y0, y0 + f(0.2), z0 + f(0.8), z0 + f(1.9))
            for lx in (x0, x1 - f(0.3)):
                for ly in (y0, y1 - f(0.3)):
                    g.box(W, T, lx, lx + f(0.3), ly, ly + f(0.3), z0, z0 + f(0.3), skip=("z0",))
            return True
        if kind == "canopy":                                         # four-poster
            g.box(W, T, x0, x1, y0, y1, z0 + f(0.4), z0 + f(1.0))
            g.box("mat_fabric", T, x0 + f(0.15), x1 - f(0.15), y0 + f(0.15), y1 - f(0.15), z0 + f(1.0), z0 + f(1.5), skip=("z0",))
            g.box("mat_linen", T, x0 + f(0.4), x1 - f(0.4), y0 + f(0.25), y0 + f(1.2), z0 + f(1.5), z0 + f(1.75), skip=("z0",))
            g.box(W, T, x0, x1, y0, y0 + f(0.2), z0 + f(1.0), z0 + f(3.2))
            ph = min(f(6.0), ceil_z - z0 - f(0.15))
            for lx in (x0, x1 - f(0.3)):
                g.box(W, T, lx, lx + f(0.3), y1 - f(0.3), y1, z0, z0 + ph, skip=("z0", "z1"))
                g.box(W, T, lx, lx + f(0.3), y0 + f(0.2), y0 + f(0.5), z0 + f(3.2), z0 + ph, skip=("z0", "z1"))
            g.box(W, T, x0, x1, y1 - f(0.3), y1, z0 + ph - f(0.3), z0 + ph, skip=("x0", "x1"))
            g.box(W, T, x0, x1, y0 + f(0.2), y0 + f(0.5), z0 + ph - f(0.3), z0 + ph, skip=("x0", "x1"))
            return True
    return False


def _stool(g, T, cx, cy, z0, W):
    g.prism(W, T, cx, cy, 0.3 * FT, z0, z0 + 1.35 * FT, 6)
    g.prism(W, T, cx, cy, 0.7 * FT, z0 + 1.35 * FT, z0 + 1.55 * FT, 6)


def _leaf(width_m, height_m):
    lw, lh, lt = width_m - 0.04, height_m - 0.04, 0.15 * FT
    lb = Builder()
    for pts in ([(0, -lt / 2, 0), (lw, -lt / 2, 0), (lw, -lt / 2, lh), (0, -lt / 2, lh)], [(0, lt / 2, 0), (lw, lt / 2, 0), (lw, lt / 2, lh), (0, lt / 2, lh)],
                [(0, -lt / 2, 0), (0, lt / 2, 0), (0, lt / 2, lh), (0, -lt / 2, lh)], [(lw, -lt / 2, 0), (lw, lt / 2, 0), (lw, lt / 2, lh), (lw, -lt / 2, lh)],
                [(0, -lt / 2, lh), (lw, -lt / 2, lh), (lw, lt / 2, lh), (0, lt / 2, lh)]):
        lb.face("mat_door_wood", pts, [(p[0] / FT / 4, -p[2] / FT / 4) for p in pts])
    for sgn in (-1, 1):
        y = sgn * (lt / 2 + 0.01)
        hz = lh * 0.45
        lb.face("mat_door_wood", [(lw - 0.15, y, hz), (lw - 0.05, y, hz), (lw - 0.05, y, hz + 0.05), (lw - 0.15, y, hz + 0.05)], [(0, 0)] * 4)
    return lb.build()


def add_interior(cx, e, mesh, door_nodes):
    """-> (full mesh, door nodes, extra part fields {layered_nodes, interior_lights}). `mesh` is the detailed shell from worldpack_detail."""
    from shapely.geometry import Point, Polygon
    import interior_styles as ist
    lay = e["layout"]
    S = ist.get(ist.resolve_name(e, ist.scene_style(cx.pack)))
    M = S["mats"]
    styled = S["name"] != "plain"
    BEAM = {**S["beams"], "mat": M["beam"]}
    floors = int(lay["floors"])
    zf_m = (e["base_elevation_ft"] - cx.fr.z_origin_ft) * FT
    zt_m = zf_m + e["wall_height_ft"] * FT
    z_g0 = zf_m + 0.02
    floor_lvl = lambda s: z_g0 if s == 0 else zf_m + s * STOREY * FT
    ceil_bot = lambda s: (zf_m + ((s + 1) * STOREY - SLAB) * FT) if s + 1 < floors else zt_m - PLATE_DROP * FT
    B2 = lambda p: cx.B(p[0], p[1])[:2]
    rm = e["roof"]["surface"]["material"]
    # ---- 1. shell split by storey / roof
    subs = {k: v for k, v in mesh.subs.items() if k != "mat_interior_floor"}
    roof_subs, wall_subs = {}, {}
    for k, F in subs.items():
        zmax = mesh.V[F][:, :, 2].max(axis=1) if len(F) else np.zeros(0)
        isroof = np.full(len(F), k == rm) | (zmax > zt_m + 1e-6)
        if isroof.any():
            roof_subs[k] = F[isroof]
        if (~isroof).any():
            wall_subs[k] = F[~isroof]
    shell = Mesh(mesh.V, mesh.UV, wall_subs)
    zs = [zf_m + s * STOREY * FT for s in range(1, floors)]
    bands = _band_split(shell, zs) if zs else [shell]
    roof_mesh = Mesh(mesh.V, mesh.UV, roof_subs)
    nodes = []
    ex = lambda tags, s, extra=None: {"tags": tags, "storey": s, "building": e["id"], **(extra or {})}
    for s, m in enumerate(bands):
        if m.tri_count:
            nodes.append((e["id"] if s == 0 else f"{e['id']}_shell_f{s}", m, ex(["building", "shell"], s)))
    # ---- 2. interior structure per storey
    rooms = {r["id"]: r for r in lay_rooms(e)}
    cells = {s: [r for r in rooms.values() if r["floor"] == s] for s in range(floors)}
    holes = {st["to_floor"]: Polygon(st["hole"]) for st in lay["stairs"]}         # slab hole in the floor reached by the stair
    uvo = wm.uv_offset(e["id"])
    int_g = {s: _G((floor_lvl(s), uvo) if styled else None) for s in range(floors)}
    roof_g = _G((floor_lvl(floors - 1), uvo) if styled else None)
    props_g = {s: _G((floor_lvl(s), uvo) if styled else None) for s in range(floors)}
    I = lambda p: B2(p)

    def cell_polys(r, hole):
        pg = Polygon(r["polygon"]).buffer(0)
        if hole is not None and pg.intersects(hole):
            pg = pg.difference(hole)
        return [g for g in (pg.geoms if hasattr(pg, "geoms") else [pg]) if g.geom_type == "Polygon" and g.area > 0.01]

    def ring_b(g):
        return [I(p) for p in list(g.exterior.coords)[:-1]]
    # floors (storey 0 plate; upper floors slab top) and slab undersides, hole sides
    for s in range(floors):
        g = int_g[s]
        hole = holes.get(s)
        for r in cells[s]:
            for pg in cell_polys(r, hole):
                g.horiz(M["floor"], ring_b(pg), floor_lvl(s), up=True)
        if s >= 1:
            zt_slab, zb_slab = floor_lvl(s), floor_lvl(s) - SLAB * FT
            lower = holes.get(s)
            for r in cells[s - 1]:
                for pg in cell_polys(r, lower):
                    g.horiz(M["ceiling"], ring_b(pg), zb_slab, up=False)
                    _beams(g, pg, I, zb_slab, e["id"], BEAM if styled else None)
                    if lower is not None:           # vertical faces around the stairwell hole (not where the hole meets a wall)
                        rb = ring_b(pg)
                        ar = sum(_cross2(rb[i], rb[(i + 1) % len(rb)]) for i in range(len(rb)))
                        cs = list(pg.exterior.coords)
                        for i in range(len(cs) - 1):
                            a, b2 = cs[i], cs[i + 1]
                            mid = Point((a[0] + b2[0]) / 2, (a[1] + b2[1]) / 2)
                            if lower.exterior.distance(mid) < 0.03 and not any(Polygon(c["polygon"]).exterior.distance(mid) < 0.03 for c in cells[s - 1]):
                                pa, pb = I(a), I(b2)
                                dv = (pb[0] - pa[0], pb[1] - pa[1])
                                out = (dv[1], -dv[0]) if ar > 0 else (-dv[1], dv[0])
                                g.fout(M["wall"], [(pa[0], pa[1], zb_slab), (pb[0], pb[1], zb_slab), (pb[0], pb[1], zt_slab), (pa[0], pa[1], zt_slab)], np.array([out[0], out[1], 0.0]))
    # top ceiling plate + beams -> roof node
    ztop_b = ceil_bot(floors - 1)
    for r in cells[floors - 1]:
        for pg in cell_polys(r, None):
            roof_g.horiz(M["ceiling"], ring_b(pg), ztop_b, up=False)
            roof_g.horiz(M["ceiling"], ring_b(pg), ztop_b + PLATE_T * FT, up=True)
            _beams(roof_g, pg, I, ztop_b, e["id"], BEAM if styled else None)
    # partitions + interior doors
    doors = {d["id"]: d for d in e["doors"]}
    new_doors = []
    for k, w in enumerate(lay["walls"]):
        s = w["floor"]
        g = int_g[s]
        A, Bp = np.array(B2(w["a"])), np.array(B2(w["b"]))
        L = float(np.linalg.norm(Bp - A))
        d = (Bp - A) / L
        nrm = np.array([-d[1], d[0]])
        t = PART_T * FT / 2
        ext = 0.1 * FT
        z0 = floor_lvl(s)
        ztop = ceil_bot(s) - (0.03 + 0.012 * (k % 4)) * FT
        cuts = []
        for did in w["doors"]:
            dd = doors[did]
            pb = np.array(B2(dd["point"]))
            u = float(np.dot(pb - A, d))
            cuts.append((u - dd["width_ft"] * FT / 2, u + dd["width_ft"] * FT / 2, dd))
        cuts.sort(key=lambda c: c[0])

        def X(u, v, z):
            p = A + d * u + nrm * v
            return (p[0], p[1], z)
        spans = []
        cur = -ext
        for u0, u1, dd in cuts:
            spans.append((cur, u0))
            cur = u1
        spans.append((cur, L + ext))
        for sg in (-1, 1):
            hint = np.array([nrm[0] * sg, nrm[1] * sg, 0.0])
            for a_, b_ in spans:
                if b_ - a_ > 1e-6:
                    g.fout(M["wall"], [X(a_, sg * t, z0), X(b_, sg * t, z0), X(b_, sg * t, ztop), X(a_, sg * t, ztop)], hint)
            for u0, u1, dd in cuts:
                zh = z0 + DOOR_H * FT
                g.fout(M["wall"], [X(u0, sg * t, zh), X(u1, sg * t, zh), X(u1, sg * t, ztop), X(u0, sg * t, ztop)], hint)
        g.fout(M["wall"], [X(-ext, -t, ztop), X(L + ext, -t, ztop), X(L + ext, t, ztop), X(-ext, t, ztop)], np.array([0, 0, 1.0]))
        if S.get("posts"):                                    # exposed timber posts at the partition ends and beside every doorway
            pu = [(-0.25 * FT, 0.25 * FT)] + [(L - 0.25 * FT, L + 0.25 * FT)]
            for u0, u1, dd in cuts:
                pu += [(u0 - 0.32 * FT, u0 - 0.02 * FT), (u1 + 0.02 * FT, u1 + 0.32 * FT)]
            for ua_, ub_ in pu:
                g.box(M["beam"], lambda lx, ly, A=A, d=d, nrm=nrm: (A[0] + d[0] * lx + nrm[0] * ly, A[1] + d[1] * lx + nrm[1] * ly), ua_, ub_, -(t + 0.07 * FT), t + 0.07 * FT, z0, ztop + 0.01, skip=("z0",))
        for u0, u1, dd in cuts:
            zh = z0 + DOOR_H * FT
            for uu, sgn in ((u0, 1), (u1, -1)):
                g.fout(M["wall"], [X(uu, -t, z0), X(uu, t, z0), X(uu, t, zh), X(uu, -t, zh)], np.array([d[0] * sgn, d[1] * sgn, 0.0]))
            g.fout(M["wall"], [X(u0, -t, zh), X(u1, -t, zh), X(u1, t, zh), X(u0, t, zh)], np.array([0, 0, -1.0]))
            # leaf: hinge at u0, swings into the first listed room's side (nrm side +)
            leaf = _leaf(u1 - u0, DOOR_H * FT)
            V = leaf.V
            Vb = np.stack([V[:, 0] * d[0] + V[:, 1] * nrm[0], V[:, 0] * d[1] + V[:, 1] * nrm[1], V[:, 2]], 1)
            hx, hy, hz = X(u0 + 0.02, 0.0, z0 + 0.02)
            new_doors.append({"id": dd["id"], "hinge": (hx, hy, hz), "mesh": Mesh(Vb, leaf.UV, leaf.subs),
                              "extras": {"isDoor": True, "doorId": dd["id"], "doorStyle": 1, "doorAnimateAngle": 1.5708, "building": e["id"], "interior": True, "storey": s,
                                         "tags": ["interior", "door"]}})
    # stairs
    for st in lay["stairs"]:
        _stair(int_g[st["from_floor"]], st, I, floor_lvl(st["from_floor"]), floor_lvl(st["to_floor"]))
    # props + lights
    lights = []
    occupied = {s: [] for s in range(floors)}
    for fi, fx in enumerate(lay["fixtures"]):
        s = fx["floor"]
        if styled and (fx["type"] in S.get("drop_types", []) or (S.get("thin") and fx["type"] not in ("hearth", "bed", "table") and fi % S["thin"] == 1)):
            continue
        a = math.radians(fx["angle_deg"])
        c, sn = math.cos(a), math.sin(a)
        px, py = fx["point"]

        def T(lx, ly, px=px, py=py, c=c, sn=sn):
            return B2((px + (lx * c - ly * sn) / FT, py + (lx * sn + ly * c) / FT))
        _fixture(props_g[s], T, fx["type"], fx["size_ft"][0], fx["size_ft"][1], fx["size_ft"][2], fx["material"], floor_lvl(s), ceil_bot(s) - 0.05 * FT, S)
        if styled:
            occupied[s].append((fx, Polygon(_rect(px, py, fx["size_ft"][0], fx["size_ft"][1], a))))
    if styled:
        _decorate(e, S, lay, rooms, occupied, props_g, B2, floor_lvl, ceil_bot, floors)
    for lt in lay["lights"]:
        lights.append({**lt, "z_abs_ft": e["base_elevation_ft"] + lt["z_ft"] + (lt["floor"] * STOREY if lt["type"] == "hearth" else 0.0)})
    # ---- 3. assemble
    for s in range(floors):
        m = int_g[s].build()
        if m.tri_count:
            nodes.append((f"{e['id']}_int_f{s}", m, ex(["interior"], s)))
    rm_ = Mesh(roof_mesh.V, roof_mesh.UV, roof_mesh.subs)
    rg = roof_g.build()
    roof_all = wm.merge_meshes([rm_, rg]) if rg.tri_count else rm_
    if roof_all.tri_count:
        nodes.append((f"{e['id']}_roof", roof_all, ex(["building", "roof"], floors - 1)))
    for s in range(floors):
        m = props_g[s].build()
        if m.tri_count:
            nodes.append((f"{e['id']}_props_f{s}", m, ex(["interior", "prop"], s, {"prop": True})))
    full = wm.merge_meshes([m for _, m, _ in nodes])
    return full, list(door_nodes) + new_doors, {"layered_nodes": nodes, "interior_lights": lights}


def _rect(cx, cy, sx, sy, ang):
    c, s = math.cos(ang), math.sin(ang)
    return [(cx + (lx * c - ly * s), cy + (lx * s + ly * c)) for lx, ly in ((-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2))]


def _decorate(e, S, lay, rooms, occupied, props_g, B2, floor_lvl, ceil_bot, floors):
    """Style decor placed around the layout's furniture with rejection tests (inside the room, clear of the other props and the stairs): stools at tables, a rag rug under
    the table, drying herbs / hanging pots over the hearth, straw on earth floors. Deterministic per building. All of it lands in the `_props_f<s>` node."""
    import random
    from shapely.geometry import LineString, Polygon
    M = S["mats"]
    rng = random.Random(int(lay.get("seed", 0)) ^ 0x5EED)
    stair_polys = []
    for st in lay["stairs"]:
        stair_polys += [LineString([st["start"], st["end"]]).buffer(st["width_ft"] / 2 + 0.8), Polygon(st["hole"]).buffer(0.5)]
    for s in range(floors):
        g = props_g[s]
        z0 = floor_lvl(s)
        fxs = occupied[s]
        blocked = [p for _, p in fxs] + list(stair_polys)
        rooms_s = [r for r in rooms.values() if r["floor"] == s]

        def room_of(fx):
            return next((r for r in rooms_s if r["id"] == fx.get("room")), None)

        def free(poly, rm, keep=()):
            if rm is None or not Polygon(rm["polygon"]).buffer(-0.25).contains(poly):
                return False
            return not any(p.intersects(poly) for p in blocked if all(p is not k for k in keep))

        for fx, fpoly in fxs:
            a = math.radians(fx["angle_deg"])
            c, sn = math.cos(a), math.sin(a)
            px, py = fx["point"]
            to_w = lambda lx, ly, px=px, py=py, c=c, sn=sn: (px + lx * c - ly * sn, py + lx * sn + ly * c)
            T = lambda lx, ly, px=px, py=py, c=c, sn=sn: B2((px + (lx * c - ly * sn) / FT, py + (lx * sn + ly * c) / FT))
            rm = room_of(fx)
            sx, sy = fx["size_ft"][0], fx["size_ft"][1]
            if fx["type"] == "table":
                if S.get("rug") and not fx.get("_rug"):
                    for pad in (1.6, 0.9):
                        rp = Polygon(_rect(*to_w(0, 0), sx + 2 * pad + 1.0, sy + 2 * pad, a))
                        if free(rp, rm, keep=[fpoly] + [p for f2, p in fxs if f2["type"] == "bench" and f2.get("room") == fx.get("room")]):
                            rx, ry = (sx + 2 * pad + 1.0) / 2 * FT, (sy + 2 * pad) / 2 * FT
                            g.box("mat_int_rug", T, -rx, rx, -ry, ry, z0 + 0.005, z0 + 0.06 * FT, skip=("z0",))
                            break
                n_st = int(S.get("stools", 0))
                spots = [(-(sx / 2 + 1.1), 0.0), (sx / 2 + 1.1, 0.0)]
                for lx, ly in spots[:n_st]:
                    wx, wy = to_w(lx, ly)
                    sp = Polygon(_rect(wx, wy, 1.5, 1.5, a))
                    if free(sp, rm):
                        _stool(g, T, lx * FT, ly * FT, z0, "mat_furn_wood")
                        blocked.append(sp)
            elif fx["type"] == "hearth" and S.get("hanging"):
                for k in range(int(S["hanging"])):
                    ly = 3.2 - sy / 2 + 2.0 * k
                    ww = 5.0
                    rp = Polygon(_rect(*to_w(0, ly), ww + 0.4, 0.6, a))
                    if rm is None or not Polygon(rm["polygon"]).buffer(-0.3).contains(rp):
                        continue
                    zr = ceil_bot(s) - (S["beams"]["h_ft"] + 0.6) * FT
                    g.box(M["beam"], T, -ww / 2 * FT, ww / 2 * FT, (ly - 0.06) * FT, (ly + 0.06) * FT, zr, zr + 0.12 * FT)
                    for lx in (-ww / 2 + 0.3, ww / 2 - 0.3):
                        g.box("mat_iron", T, lx * FT - 0.02 * FT, lx * FT + 0.02 * FT, (ly - 0.02) * FT, (ly + 0.02) * FT, zr + 0.12 * FT, ceil_bot(s) - 0.02 * FT, skip=("z0", "z1"))
                    for j, lx in enumerate((-1.6, -0.6, 0.5, 1.6)):
                        if j == 3:
                            g.prism("mat_iron", T, lx * FT, ly * FT, 0.4 * FT, zr - 0.5 * FT, zr, 8)
                        else:
                            g.prism("mat_herb" if j != 1 else "mat_pottery", T, lx * FT, ly * FT, 0.2 * FT, zr - (1.0 if j != 1 else 0.7) * FT, zr, 5)
        n_patch = int(S.get("straw_patches", 0))
        if n_patch:
            for r in rooms_s:
                pg = Polygon(r["polygon"]).buffer(-0.5)
                if pg.is_empty or pg.area < 12:
                    continue
                tries = 0
                made = 0
                minx, miny, maxx, maxy = pg.bounds
                while made < n_patch and tries < 30:
                    tries += 1
                    cx_, cy_ = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
                    ang = rng.uniform(0, math.pi)
                    rp = Polygon(_rect(cx_, cy_, rng.uniform(1.8, 3.0), rng.uniform(1.4, 2.2), ang))
                    if not pg.contains(rp) or any(p.intersects(rp) for p in blocked):
                        continue
                    ring = [B2(p) for p in list(rp.exterior.coords)[:-1]]
                    g.horiz("mat_straw", ring, z0 + 0.04 * FT, up=True)
                    made += 1


def lay_rooms(e):
    return e.get("rooms") or []


def _beams(g, pg, I, z_under, bid, B=None):
    """Ceiling joists hanging 0.5 ft below z_under across the short axis of the cell, every 3 ft. B (interior style): {spacing_ft, w_ft, h_ft, mat}."""
    sp, bw, bh, bmat = (B["spacing_ft"], B["w_ft"], B["h_ft"], B["mat"]) if B else (3.0, 0.4, 0.5, "mat_joist")
    minx, miny, maxx, maxy = pg.bounds
    from shapely.geometry import LineString
    along_x = (maxx - minx) <= (maxy - miny)          # beams span the short direction
    n = max(1, int(((maxy - miny) if along_x else (maxx - minx)) // sp))
    for k in range(n):
        off = ((miny if along_x else minx) + (k + 0.5) * ((maxy - miny) if along_x else (maxx - minx)) / n)
        ln = LineString([(minx - 1, off), (maxx + 1, off)] if along_x else [(off, miny - 1), (off, maxy + 1)])
        seg = ln.intersection(pg.buffer(-0.15))
        if seg.is_empty or seg.geom_type != "LineString" or seg.length < 1.0:
            continue
        a, b = I(seg.coords[0]), I(seg.coords[-1])
        d = np.array(b) - np.array(a)
        L = float(np.linalg.norm(d))
        d = d / L
        nrm = np.array([-d[1], d[0]])

        def T(lx, ly, a=a, d=d, nrm=nrm):
            return (a[0] + d[0] * lx + nrm[0] * ly, a[1] + d[1] * lx + nrm[1] * ly)
        g.box(bmat, T, 0.0, L, -bw / 2 * FT, bw / 2 * FT, z_under - bh * FT, z_under - 0.012, skip=("z1",))


def _stair(g, st, I, z_lo, z_hi):
    n = st["risers"]
    a, e_ = np.array(I(st["start"])), np.array(I(st["end"]))
    run = float(np.linalg.norm(e_ - a))
    d = (e_ - a) / run
    nrm = np.array([-d[1], d[0]])
    tread = run / (n - 1)
    r = (z_hi - z_lo) / n
    hw = st["width_ft"] * FT / 2

    def P(s, v, z):
        p = a + d * s + nrm * v
        return (p[0], p[1], z)
    for i in range(n - 1):                                   # risers 0..n-2 (the last riser is the slab edge) and treads
        s0 = i * tread
        g.fout("mat_furn_wood", [P(s0, -hw, z_lo + i * r), P(s0, hw, z_lo + i * r), P(s0, hw, z_lo + (i + 1) * r), P(s0, -hw, z_lo + (i + 1) * r)], np.array([-d[0], -d[1], 0.0]))
        g.fout("mat_furn_wood", [P(s0, -hw, z_lo + (i + 1) * r), P(s0 + tread, -hw, z_lo + (i + 1) * r), P(s0 + tread, hw, z_lo + (i + 1) * r), P(s0, hw, z_lo + (i + 1) * r)], np.array([0, 0, 1.0]))
    prof = [(0.0, 0.0)] + [(0.0, r)]
    for i in range(1, n):
        prof += [(i * tread, i * r), (i * tread, (i + 1) * r)] if i < n - 1 else [(i * tread, i * r)]
    prof += [((n - 1) * tread, 0.0)]
    idx = wm.earclip(prof)
    for sg in (-1, 1):
        for ia, ib, ic in idx:
            pts = [P(prof[k][0], sg * hw, z_lo + prof[k][1]) for k in (ia, ib, ic)]
            g.fout("mat_joist", pts, np.array([nrm[0] * sg, nrm[1] * sg, 0.0]))


def pad_buildings(pack, h):
    """Level pads under every building (interiors or not) and an apron in front of each door: cut only, blended out over a few cells (building_ground.py)."""
    import building_ground as bg
    return bg.pad_heights(pack, h)
