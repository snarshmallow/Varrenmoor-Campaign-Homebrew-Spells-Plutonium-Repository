"""Simple 3D models for the quest loot items (small props, lying flat on the ground, origin at the floor centre). One generator file per
item (item_<slug>.py) calls build_item(k, slug)."""
import math

from _runes import put

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange/Items"


def build_item(k, slug):
    paper = k.mat("it_paper", (0.86, 0.8, 0.62), roughness=0.95)
    paper2 = k.mat("it_paper_old", (0.7, 0.6, 0.4), roughness=0.95)
    ink = k.mat("it_ink", (0.07, 0.06, 0.06), roughness=0.9)
    brass = k.mat("it_brass", (0.62, 0.45, 0.14), roughness=0.4, metallic=0.9)
    tin = k.mat("it_tin", (0.5, 0.52, 0.55), roughness=0.5, metallic=0.8)
    bone = k.mat("it_bone", (0.85, 0.8, 0.68), roughness=0.8)
    red = k.mat("it_red", (0.45, 0.07, 0.06), roughness=0.8)
    leather = k.mat("it_leather", (0.25, 0.14, 0.08), roughness=0.85)
    string = k.mat("it_string", (0.6, 0.5, 0.35), roughness=1.0)
    wax = k.mat("it_wax", (0.5, 0.05, 0.05), roughness=0.5)
    card = k.mat("it_card", (0.9, 0.88, 0.8), roughness=0.9)
    fur = k.mat("it_fur", (0.35, 0.3, 0.28), roughness=1.0)
    B = lambda x, y, z, sx, sy, sz, m, n="part", rz=0.0: k.box((sx, sy, sz), loc=(x, y, z), rot=(0, 0, rz), material=m, name=n)

    if slug == "rune_slip":
        B(0, 0, 0.003, 0.12, 0.2, 0.006, paper, "slip")
        # a 'Q.' in the corner (ring + tail + dot) and loose doodles that look like pieces of runes
        k.cylinder(0.011, 0.002, loc=(-0.035, -0.075, 0.0066), material=ink, name="q_ring", verts=14)
        k.cylinder(0.007, 0.0025, loc=(-0.035, -0.075, 0.0067), material=paper, name="q_hole", verts=12)
        B(-0.026, -0.086, 0.0066, 0.014, 0.004, 0.002, ink, "q_tail")
        B(-0.012, -0.088, 0.0066, 0.004, 0.004, 0.002, ink, "q_dot")
        for (x, y, ln, rot) in ((0.02, 0.06, 0.05, 90), (0.035, 0.07, 0.03, 40), (0.035, 0.05, 0.03, -40), (-0.03, 0.03, 0.045, 90),
                                (-0.018, 0.045, 0.03, 35), (0.01, -0.01, 0.04, 20), (0.0, -0.025, 0.03, -60), (0.04, -0.045, 0.04, 90)):
            B(x, y, 0.0066, 0.002, ln, 0.002, ink, "doodle", rot)
    elif slug == "clinic_tag":
        B(0, 0, 0.0015, 0.05, 0.07, 0.003, tin, "tag", 12)
        k.cylinder(0.006, 0.004, loc=(0, 0.03, 0.003), material=brass, name="eyelet", verts=10)
        B(0.016, -0.026, 0.004, 0.012, 0.01, 0.002, ink, "chew_mark")
    elif slug == "rat_tin":
        k.cylinder(0.055, 0.04, loc=(0, 0, 0.02), material=tin, name="tin", verts=20)
        k.cylinder(0.058, 0.01, loc=(0, 0, 0.045), material=tin, name="lid", verts=20)
        B(0.07, 0, 0.004, 0.03, 0.018, 0.002, paper, "tag", 20)
    elif slug == "notice":
        B(0, 0, 0.003, 0.22, 0.3, 0.006, paper, "notice")
        for i in range(5):
            B(0, 0.1 - 0.045 * i, 0.007, 0.15, 0.008, 0.002, ink, "text_line")
        k.cylinder(0.008, 0.02, loc=(0, 0.14, 0.01), material=brass, name="pin", verts=8)
    elif slug == "lodging_bill":
        B(0, 0, 0.003, 0.2, 0.28, 0.006, paper2, "bill")
        for i in range(6):
            B(0, 0.1 - 0.035 * i, 0.007, 0.14, 0.007, 0.002, ink, "text_line")
        B(0.04, -0.1, 0.008, 0.08, 0.04, 0.002, red, "overdue_stamp", 15)
    elif slug == "guest_book":
        B(0, 0, 0.02, 0.2, 0.28, 0.04, leather, "cover")
        B(0.005, 0, 0.02, 0.185, 0.265, 0.034, paper, "pages")
        B(-0.098, 0, 0.02, 0.012, 0.28, 0.042, leather, "spine")
        B(0.0, 0.0, 0.0415, 0.12, 0.05, 0.003, brass, "title_plate")
    elif slug == "brass_plate_6":
        # a wall plate: stands upright, front toward +y (mount it on a wall facing +y). The numeral is a real texture, not geometry.
        import bpy
        from _painting import _image_material
        B(0, 0, 0.08, 0.12, 0.012, 0.16, brass, "plate")
        mat = _image_material(k, "plate6", "item_plate6.png")
        hw, hh, y = 0.058, 0.078, 0.0066
        me = bpy.data.meshes.new("plate6_face")
        me.from_pydata([(hw, y, 0.002), (-hw, y, 0.002), (-hw, y, 0.158), (hw, y, 0.158)], [], [(0, 1, 2, 3)])
        uv = me.uv_layers.new(name="UVMap")
        for li, uvc in zip(me.polygons[0].loop_indices, ((0, 0), (1, 0), (1, 1), (0, 1))):
            uv.data[li].uv = uvc
        me.update()
        ob = bpy.data.objects.new("plate6_face", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.data.materials.append(mat)
        for sx in (-1, 1):
            for sz in (0.02, 0.14):
                k.cylinder(0.005, 0.004, loc=(sx * 0.05, 0.008, sz), rot=(90, 0, 0), material=tin, name="screw", verts=8)
    elif slug == "bone_tag":
        B(0, 0, 0.004, 0.035, 0.06, 0.008, bone, "tag", 8)
        k.cylinder(0.005, 0.01, loc=(0, 0.023, 0.004), material=ink, name="hole", verts=8)
    elif slug == "referral_card":
        B(0, 0, 0.001, 0.14, 0.09, 0.002, card, "card")
        k.cylinder(0.017, 0.003, loc=(0.045, -0.015, 0.003), material=wax, name="seal", verts=16)
        for i in range(3):
            B(-0.02, 0.025 - 0.02 * i, 0.003, 0.07, 0.005, 0.001, ink, "text_line")
    elif slug == "field_notebook":
        B(0, 0, 0.015, 0.12, 0.17, 0.03, red, "cover")
        B(0.004, 0, 0.015, 0.108, 0.158, 0.026, paper, "pages")
        B(0.05, 0, 0.016, 0.012, 0.17, 0.032, leather, "strap")
        k.sphere(0.008, loc=(0.056, 0, 0.016), material=brass, name="clasp", segments=8)
    elif slug == "loose_page":
        B(0, 0, 0.0015, 0.2, 0.27, 0.003, paper2, "page", 6)
        B(0, 0.02, 0.004, 0.1, 0.07, 0.002, ink, "box_drawing", 6)
        B(0.04, -0.07, 0.004, 0.06, 0.02, 0.002, ink, "music_staff", 6)
    elif slug == "capsule":
        k.cylinder(0.025, 0.12, loc=(0, 0, 0.025), rot=(0, 90, 0), material=brass, name="capsule", verts=18)
        for sx in (-1, 1):
            k.sphere(0.025, loc=(sx * 0.06, 0, 0.025), material=brass, name="cap_end", segments=10)
        B(0, 0, 0.052, 0.05, 0.03, 0.003, bone, "bone_tag")
        B(0.0, 0.04, 0.003, 0.05, 0.08, 0.005, paper, "letter", 20)
    elif slug == "lost_property_tag":
        B(0, 0, 0.0015, 0.06, 0.1, 0.003, paper, "tag")
        k.cylinder(0.004, 0.004, loc=(0, 0.04, 0.003), material=brass, name="eyelet", verts=8)
        B(0, 0.075, 0.0008, 0.004, 0.05, 0.002, string, "string")
        B(0, -0.01, 0.004, 0.04, 0.006, 0.001, ink, "text_line")
    elif slug == "ledger_excerpt":
        for i in range(3):
            B(0.003 * i, 0.002 * i, 0.002 + 0.004 * i, 0.2, 0.28, 0.003, paper if i else paper2, "page", 3 * i)
        B(0, 0.0, 0.0145, 0.12, 0.007, 0.002, ink, "line_a")
        B(0, -0.04, 0.0145, 0.12, 0.007, 0.002, ink, "line_b")
        B(0.04, -0.09, 0.0145, 0.03, 0.03, 0.002, red, "rat_mark")
    else:
        raise ValueError(slug)


# ---------------------------------------------------------------------------------------------------------------------------------
# generic parametric props, used by foundry-tools (vtt item): shapes paper, book, tag, tin, box, plate. p = dict(shape, w, d, h, color, texture, ...)
# w = X (m), d = plan Y (m), h = height (m). 'texture' is a PNG in foundry-3d/textures mapped on the main face. A 'plate' stands upright, face toward +y.
# ---------------------------------------------------------------------------------------------------------------------------------
def _quad(name, verts, texfile, k):
    import bpy
    from _painting import _image_material
    mat = _image_material(k, "gen_" + texfile, texfile)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for li, uvc in zip(me.polygons[0].loop_indices, ((0, 0), (1, 0), (1, 1), (0, 1))):
        uv.data[li].uv = uvc
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(mat)


def build_generic(k, p):
    shape = p.get("shape", "box")
    w, d, h = float(p.get("w", 0.1)), float(p.get("d", 0.1)), float(p.get("h", 0.05))
    col = p.get("color", "#8a6a3a").lstrip("#")
    rgb = tuple(int(col[i:i + 2], 16) / 255 for i in (0, 2, 4))
    base = k.mat("gen_base", rgb, roughness=0.8, metallic=float(p.get("metal", 0.0)))
    dark = k.mat("gen_dark", tuple(c * 0.45 for c in rgb), roughness=0.9)
    tex = p.get("texture")
    B = lambda x, y, z, sx, sy, sz, m, n="part": k.box((sx, sy, sz), loc=(x, y, z), material=m, name=n)
    if shape == "paper":
        t = 0.004
        B(0, 0, t / 2, w, d, t, base, "sheet")
        if tex:
            z = t + 0.0004
            _quad("face", [(-w / 2, -d / 2, z), (w / 2, -d / 2, z), (w / 2, d / 2, z), (-w / 2, d / 2, z)], tex, k)
    elif shape == "book":
        B(0, 0, h / 2, w, d, h, dark, "cover")
        B(0.004, 0, h / 2, w - 0.02, d - 0.012, h - 0.012, base, "pages")
        B(-w / 2 + 0.006, 0, h / 2, 0.012, d, h + 0.002, dark, "spine")
        if tex:
            z = h + 0.0004
            _quad("face", [(-w / 2, -d / 2, z), (w / 2, -d / 2, z), (w / 2, d / 2, z), (-w / 2, d / 2, z)], tex, k)
    elif shape == "tag":
        B(0, 0, h / 2, w, d, h, base, "tag")
        k.cylinder(min(w, d) * 0.1, h + 0.001, loc=(0, d * 0.35, h / 2), material=dark, name="hole", verts=10)
    elif shape == "tin":
        k.cylinder(w / 2, h, loc=(0, 0, h / 2), material=base, name="tin", verts=20)
        k.cylinder(w / 2 + 0.003, h * 0.2, loc=(0, 0, h), material=dark, name="lid", verts=20)
    elif shape == "plate":
        B(0, 0, h / 2, w, 0.012, h, base, "plate")
        if tex:
            _quad("face", [(w / 2, 0.0066, 0.002), (-w / 2, 0.0066, 0.002), (-w / 2, 0.0066, h - 0.002), (w / 2, 0.0066, h - 0.002)], tex, k)
    else:
        B(0, 0, h / 2, w, d, h, base, "box")
        B(0, 0, h * 0.5, w + 0.004, 0.03, h * 0.2, dark, "band")
        B(0, 0, h + 0.004, w * 0.9, d * 0.9, 0.008, dark, "lid")
