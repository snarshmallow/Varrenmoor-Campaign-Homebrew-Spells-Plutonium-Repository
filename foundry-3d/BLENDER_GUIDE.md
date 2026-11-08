# Working on Bridgehollow models in Blender (plain-language guide)

Blender 5.2 is at `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`. Units are metres, Z is up, X east, Y north.
Every object is named by its entity id (for example `bld_house_044`), and its origin is its pivot (bottom centre), so moving or rotating it keeps the Foundry placement correct.

## 1. Open a place in Blender
From a terminal in the repo folder:

    "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --factory-startup --python foundry-3d/blender/import_worldpack.py -- world/bridgehollow__dyers_walk_local/export --blend D:\scratch\dyers.blend

(Use `world/bridgehollow/export` for the whole bowl, which is big; `--layers terrain,buildings` loads only some layers.)
Then open `D:\scratch\dyers.blend` normally. The Outliner (top right) shows a Collection per layer: terrain, buildings by district, roads, foliage.

## 2. Edit
- Click an object in the Outliner, or in the viewport, then press `N` and open the Item tab to see location, rotation, scale.
- Move `G`, rotate `R`, scale `S`. Press `Tab` for Edit Mode to change the mesh; `Tab` again to leave.
- Keep each object's origin where it is. Do not apply or reset location, and do not rename objects (names are ids).
- The Object Properties tab > Custom Properties shows `wp_id`, `wp_layer` and `wp_type`. Leave them.
- Doors are separate objects with a hinge at their origin. Rotate on Z to open them. Keep one material per door.
- Add new props as new objects inside the right Collection (give a `wp_layer` custom property of `prop` so the split exporter can tag it).
- Save with `Ctrl+S`.

## 3. Write your edits back (split GLBs)

    "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b D:\scratch\dyers.blend --python foundry-3d/blender/export_worldpack_split.py -- world/bridgehollow__dyers_walk_local/export --ids bld_house_044

`--ids` re-exports only the named objects. Leave it out to export everything. File names, ids and pivots stay the same, so nothing moves in Foundry.

## 4. Merge/compress and push
    python illustrator/generators/worldpack_split.py merge --preset layer       (fewer, bigger models; faster in Foundry)
    python illustrator/generators/worldpack_split.py publish --preset layer --scene-uuid Scene.xxxx --dry-run
Drop `--dry-run` to push. The Claude coordinator will usually run these for you; just tell it which objects you changed.

## 5. Quick previews without opening Blender
`foundry-3d/blender/preview.py`, `street_preview.py` and `interior_preview.py` render PNGs headless.

## Tips
- Terrain is one big mesh: sculpt gently and keep road beds, which are graded into it. Roads sit 0.25 m above it on purpose (no coplanar surfaces).
- Foundry shows a model correctly only if its pivot and scale are untouched. If something lands wrong, tell Claude the object id.
- Textures live in the shared `textures/` folder next to the GLBs and stay PNG.
