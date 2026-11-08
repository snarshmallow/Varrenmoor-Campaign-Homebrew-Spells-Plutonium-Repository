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
