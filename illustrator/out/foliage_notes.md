# Foliage (GUI + merge for Foundry), notes

Files: generators/foliage.py (model, scatter, 2D, merge, CLI), foliage_mesh.py (species meshes, atlas), presets/foliage/{trees,shrubs,ground,mixes}.json,
panel/lib/foliage.js + panel/foliage_ui.js (+ delimited edits in index.html, main.js), foundry-3d/blender/foliage_preview.py, tests: generators/test_foliage.py,
panel/test/test_foliage_jobs.js. Small edits: worldpack.py (scatter items keep their id/kind), worldpack_split.py (merge/publish --foliage).

Data: world/<place>/foliage.json, feet, ids fol_<zone>_nnnn (counters stored, never reused). Regenerating a zone replaces only its generated items;
hand-placed (src "hand") stay and keep spacing. `foliage.py export` / scatter also write world/<place>/scatter/foliage.json so the pack 'foliage' entities have the same ids.
2D: layer "DETAILS - Foliage" (own layer so region-extract trees are not wiped), one path per entity id.
Env var VB_FOLIAGE_JSON redirects the data file (tests, scratch).

Merge: per spatial chunk (default 150 ft) ONE GLB, ONE mesh, ONE primitive, shared atlas material (alpha-cut MASK), plus .lod1/.lod2 (impostor crossed quads) files;
budget thinning (ground cover first, hand-placed last), optional impostor/low-LOD beyond a distance from the scatter centroid, gltfpack "quant" (KHR_mesh_quantization only; meshopt available but may not load).
Foliage is never mixed with buildings, so the gltfpack door-node issue does not apply.

Benchmark (3145 instances, 2023 trees, Bridgehollow pack, chunk 200 ft; illustrator/out/foliage/bench_report.json):
| | files | draw calls | triangles | GLB |
| unmerged (tile per tree) | 7 templates + 3145 tiles | 5168 | 197,870 | templates 25 KB |
| merged | 50 chunks | 50 | 197,870 | 7.4 MB (+LODs 11.3 MB) |
| merged, budget 120k | 50 | 50 | 119,964 (1797 thinned) | 4.4 MB |
| merged, impostors >900 ft, LOD1 >450 ft | 50 | 50 | 95,706 | 3.9 MB |
| merged, quant | 50 | 50 | 197,870 | 3.8 MB (+LODs 5.8 MB) |
Draw calls for the unmerged case are estimated (primitives per template x tiles). Merged GLBs are bigger than the shared templates because geometry is baked per tree.

Visual: illustrator/out/foliage/dyers_3d_{aerial,street,close}.png (Blender, 650 instances on Dyers Walk terrain, rendered before oak/beech crowns were reduced), dyers_2d_preview.png.
Foundry: pushed 9 merged chunk tiles to ZZ Dyers Walk 3D Test (Scene.sFd94FxO1JX8dlJg) and re-set the skybox. NOT viewed: the only open browser tab is another scene (ZZ Padding Test) and I did not switch the user's view; no fps measured; whether 3D Canvas renders alpha-cut atlas cards and quantized GLBs for foliage is unverified.
Publish: `foliage.py publish --place P --scene-uuid Scene.x [--dry-run]` or `worldpack_split.py publish --preset layer --foliage ...`.
Not done: panel inside Illustrator not exercised live (only node mock + syntax check); tile placement scale depends on scene calibration like other models.

## v2 trees (crossed-card crowns, painted atlas, Baileywiki imports)
Why: v1 crowns were solid low-poly blobs. v2 builds every tree from a bark skeleton plus clusters of alpha-cut leaf-spray cards, so sky and branches show through.
- Atlas (foliage_tex.py, foliage_mesh.write_atlas): 2048x1536, 8x6 slots of 256 px. Painted leaf sprays (oak, beech, birch, maple, willow strands, rowan compound leaves,
  bush/box, ivy), spruce/fir and juniper needle sprays, scots-pine needle fans, grass/reed/fern/flowers, furrowed bark (3 kinds), dense-foliage core, rock, impostors.
  Each leaf is painted with a dark edge, mid body, lit half, midrib and veins, per-leaf colour variation and a few backlit yellow leaves; baked AO darkens each card toward its stem root.
  Seasons: `--season summer|autumn|winter` (also env VB_FOLIAGE_SEASON) on atlas/merge/publish; winter = bare twigs plus a few dead leaves. Alpha is anti-aliased; material alphaMode MASK cutoff 0.5, double sided (no sorting problem); colour is bled into transparent texels (no fringes).
- Meshes (foliage_mesh.py): tapered trunk with root flare and buttress roots, 3-segment limbs plus children (bark tube, UV once around), 2 crossed spray cards per cluster placed in the outer 40-85% of the crown
  (habits: round, oval, weep with hanging strands, pine = tufts on a long bare trunk), conifers = tiers of two drooping card rings plus leader tuft and an opaque core, shrubs/hedges = cards around a small opaque core.
  Every vertex has an explicit spherical normal (outward + a little up, so crowns shade as soft volumes) and COLOR_0 (AO: darker inside/low, per-cluster tint). Needs worldpack_mesh.Mesh N/C (added, optional, other callers unaffected).
  Cards are one segment (2 tris). LOD0 about 350-700 tris per tree (v1: 50-200), LOD1 about 1/3, LOD2 two crossed impostor quads (painted impostor tiles).
- Imported (foliage_import.py, third_party/baileywiki/*.npz+png): found by listing Foundry data through the GM client (FilePicker) and read from `\VEGA\C\FoundryVTT resources\Data` (read-only); source
  baileywiki-content/assets/modules/baileywiki-3d/models/2025/02-february/trees/frontier-europeanbeech-xl-02.gltf (+zz-meshes, zz-textures) and
  .../maps-modular/ancient-castle/foliage-debris-clutter-etc/ancient-ash-tree-01/03.glb, ancient-bush-01/03.glb. All Draco; dumped via foundry-3d/blender/dump_gltf_npz.py. Raw copies stay in
  illustrator/out/foundry_trees/ (not committed). Species beech_bw (30.6k tris, hero: its canopy is 8.5k real photo-scan spray cards, LOD1 9k), ash_bw (9.3k), ash_small_bw (540), bush_bw1 (650), bush_bw3 (115).
  Scaled to nominal height, pivot at trunk base, root part below ground cut, bark UVs (tiling in the original) folded into one bark tile, textures resized into the shared atlas. The original normal maps and the beech knot decals are not used. Private use only (never distributed). Not in any mix; add with `add --species beech_bw` or put into a mix.
- Sheets/renders: illustrator/out/foliage/species_sheet.py (python builds one GLB per species, Blender renders, montage) -> v2_species_sheet_{summer,autumn,winter}.png; Dyers Walk: v2_dyers_{aerial,street,close}.png (foundry-3d/blender/foliage_preview.py).
- Cost (bench, 3145 instances, same scatter as v1): triangles 1.12M (v1 198k), 50 chunk GLBs, 40.7 MB quantized (74 MB plain, 96.7 MB with LODs), with impostor ring 491k tris, budget cap 120k keeps ~7% of the instances. So use the budget / impostor distance for big forests; v2 is about 5x the triangles for a far better look.
  Dyers Walk (653 instances): 122.5k tris, 9 chunks, 8.1 MB (v1 about 40k tris).
- Not done: normal maps (single base-colour atlas only; the glTF material has no normalTexture), per-card wind, KHR_materials_transmission for backlight (backlight is only painted), double-sided custom normals flip on back faces in three.js (blended 65/35 toward the spherical normal in imports, mild elsewhere).
- Foundry: re-published the merged Dyers foliage (9 tiles, foliage_v002) to ZZ Dyers Walk 3D Test (Scene.sFd94FxO1JX8dlJg) using FOUNDRY_ASSETS_DIR=`\VEGA\C\FoundryVTT resources\Data\assets\varrenmoor-3d` (the old `\VEGA\varrenmoor-3d` share name no longer resolves from this PC). NOT viewed in Foundry: the only GM tab belonged to the padding agent, so no screenshots; whether 3D Canvas honours COLOR_0 and MASK for these GLBs is unverified (Blender renders honour both).
