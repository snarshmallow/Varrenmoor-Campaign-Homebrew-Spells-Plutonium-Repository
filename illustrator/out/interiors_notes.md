# House interiors and layouts (2026-11-07)

Status: generated, deterministic, NOT canon, NOT tested in Foundry. Test place: `world/bridgehollow__dyers_walk_local` (25 houses, 16 one-storey, 9 two-storey).

## What exists
* `illustrator/generators/interiors.py` - layout generator. Seed = sha1("interior:" + entity id). Per building: seeded binary partition of the footprint (inner polygon, exterior wall 0.75 ft)
  into rooms in the oriented-bounding-box frame; the room holding the exterior door is the entry room (Hall / Common room / Shop floor ...); upper storeys reuse the ground cells.
  Kinds known: house, cottage, inn, tavern, workshop, shop, mill, barn, stable, civic (+ aliases); unknown kinds use the house recipe. Only `house` has been exercised on the real pack.
  Output (world feet): `rooms` (id, name, floor, polygon, area, use, doors), `doors` (exterior from the region detail pass + generated interior doors, 3.0 x 6.8 ft, spanning tree over the rooms, one loop for big houses),
  `layout` = walls (partitions, 0.4 ft), stairs (straight, 16 risers of 7.5 in, 9 ft run, hole polygon for the slab, 2.5 ft free beside it, kept clear of the door swing and of every door), windows,
  fixtures (bed, table, bench, hearth, shelf, chest, barrel, crate, counter, workbench, desk, hay), light hints (hearth, window light).
  CLI: `python illustrator/generators/interiors.py generate --place P [--only ID] [--force]` writes `rooms`, `doors`, `layout` into `world/P/buildings/*.json` (hand-authored rooms are not overwritten without --force).
  `worldpack.export_world` uses the stored layout, else generates one on the fly for buildings that have exterior doors (region children); `export/entities/buildings.json` then carries `rooms`, `doors`, `layout`.
* `interiors_render.py` - floor plan SVG + PNG at 20 px/ft (5 ft per 100 px, i.e. 5 ft/in at 100 dpi), one panel per storey, plus a street sheet (ground floors in true position at 10 px/ft with the road outlines).
  `python illustrator/generators/interiors.py plans --place P --out DIR`. Output here: `illustrator/out/interiors/plans/<id>_plan.png|svg` (25) and `bridgehollow__dyers_walk_local_street_plan.png|svg`.
  The SVG keeps text as text so it can become an Illustrator layer; no panel job was run (not asked for).
* `worldpack_interiors.py` - 3D. Glb nodes per building (`<id>` ground shell, `<id>_shell_fN`, `<id>_int_fN` floors/slabs/ceiling joists/partitions/stairs, `<id>_roof` incl. top ceiling plate, `<id>_props_fN` furniture
  with extras tag `prop`, `<id>_idoor_fS_N` interior door leaves with `isDoor`/`doorAnimateAngle 90`, origin on the hinge). The exterior door leaf is still its own hinge node and now has a room behind it.
  Toggle for cutaway: hide `_roof`, then `_shell_f<n>`/`_int_f<n>`/`_props_f<n>` from the top. Hooks (all guarded by `e.get("layout")`): `worldpack_mesh.build_parts`, `worldpack_detail` (windows + materials),
  `worldpack_split._entry` (layered nodes, `lights` in placements.json, each with `foundry_px`, colour, bright/dim ft).
* Previews (Blender 5.2, `foundry-3d/blender/interior_preview.py`): `illustrator/out/interiors/cutaway/dyers_<id>_cut_top|cut_ground|cut_low.png` (houses 044, 064, 087) and `dyers_street_cutaway.png`.
* Tests: `python illustrator/generators/test_interiors.py` (room coverage and no overlap, doors connected per storey, stairs reach every floor and sit inside the room on both floors and clear of doors, fixtures inside rooms,
  windows on the footprint, determinism, JSON round trip, all 25 real buildings, 3D node split/doors/props, z-band splitting, renderer).

## Real vs generated, canon vs not
Everything here is generated and non-canon (`generated: true, canon: false`); the footprints, floors and kinds are the only inputs from the world data, the exterior door positions come from the (also non-canon) region detail pass.
No room, door or furniture is canon; a human edit should drop the `generated` flag in `layout` so `generate` keeps it.

## Changes you will notice
* Windows are now the layout's windows (same rule as before: ~1 per 8 ft of free wall, 3 x 3.5 ft, sill 3.5 ft, per storey) minus those landing on a partition end or behind the stair: 52 instead of 103 on this street.
* Interior structure adds ~10 000 triangles (street total 59.5k, buildings 21.5k, largest building GLB 131 KB).
* Terrain under houses with a layout is cut down to the floor level (`pad_buildings`, cut only, blended over 4 cells) so it never pokes through the floor. This changes the terrain GLB for those places (a shallow trench up to ~1 ft around uphill walls).
* `DETAIL_MATS` gains flat-colour interior materials (furniture wood, fabric, straw, hearth stone, ember, joists, ceiling). They have no textures; the materials/texture agent may replace them.

## Known limits / not done
* Not verified in Foundry: node names, `tags`/`prop` extras, interior `isDoor` nodes (sign of `doorAnimateAngle` untested), `lights` in placements.json (nothing creates Foundry light documents or walls from them yet).
* `worldpack_split.py merge`: door leaves are kept as nodes now (another agent's change), but the storey/roof/props split is not preserved by merging (untested); use the split GLBs for cutaway. `import_worldpack.py` (Blender scene importer) does not build interiors; use the split GLBs/`interior_preview.py`.
* The regenerated `world/.../export/` (pack, GLBs, placements) is NOT committed (it also contains another agent's texture work); re-run `worldpack.py export` + `worldpack_split.py split` to get the interiors in the GLBs.
* One straight stair per building; no L/U stairs, no cellars, attics, chimneys on the exterior, balconies or ladders. Stairs against the stair-side wall of a window lose that window.
* Partition tops stop 0.03-0.07 ft below the ceiling (no coplanar faces), so there is a hairline gap. Interior doors have no frames, only plain jambs. The ground floor plate sits 2 cm above the nominal floor, exterior door sills are at the nominal floor.
* Furniture is box/prism level; hearth has no chimney outside. Light hints are not baked into the mesh.
* Rooms are rectangles clipped to the (convex quad) footprint; non-convex or very skewed footprints are only covered by the room-coverage test for convex quads. Footprints below ~25 ft2 of inner area raise `ValueError` and are skipped by `generate`.
* Child regions re-extracted from a parent regenerate details and building JSON; run `interiors.py generate` again on the child (or rely on the export-time generation).
