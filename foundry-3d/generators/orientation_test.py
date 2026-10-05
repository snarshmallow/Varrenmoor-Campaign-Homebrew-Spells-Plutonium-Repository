"""Orientation test for 3D Canvas: a plate with a red arrow toward plan-view NORTH (+Y), a blue cube EAST (+X),
a yellow pillar WEST (-X) and a green ball SOUTH (-Y). Place it in a scene at tile rotation 0 and note where each
lands on the canvas; that fixes the model-to-canvas mapping for every scene.
"""
import bpy

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"


def build(k):
    grey = k.mat("plate", (0.25, 0.25, 0.27), roughness=0.9)
    red = k.mat("arrow_red", (0.9, 0.05, 0.05), roughness=0.6, emission=(0.9, 0.05, 0.05))
    blue = k.mat("cube_blue", (0.05, 0.15, 0.95), roughness=0.6, emission=(0.05, 0.15, 0.95))
    yellow = k.mat("pillar_yellow", (0.95, 0.85, 0.05), roughness=0.6, emission=(0.95, 0.85, 0.05))
    green = k.mat("ball_green", (0.05, 0.8, 0.15), roughness=0.6, emission=(0.05, 0.8, 0.15))

    k.box((8, 10, 0.1), loc=(0, 0.5, 0.05), material=grey, name="plate")
    k.box((0.7, 4.0, 0.2), loc=(0, 1.8, 0.2), material=red, name="arrow_shaft")      # from the centre toward +Y
    # arrowhead: a triangular prism pointing +Y
    verts = [(-1.1, 3.8, 0.1), (1.1, 3.8, 0.1), (0, 5.0, 0.1), (-1.1, 3.8, 0.3), (1.1, 3.8, 0.3), (0, 5.0, 0.3)]
    faces = [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)]
    me = bpy.data.meshes.new("head")
    me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new("arrow_head", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(red)
    k.box((1.0, 1.0, 1.0), loc=(3.2, 0, 0.6), material=blue, name="east_cube")
    k.cylinder(0.4, 2.5, loc=(-3.2, 0, 1.35), material=yellow, name="west_pillar", verts=16)
    k.sphere(0.6, loc=(0, -3.6, 0.7), material=green, name="south_ball")
