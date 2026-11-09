# Europa Valwater: 3D token

## v2 (current): level head, cape down her back, portrait face
The actor now uses `assets/varrenmoor-3d/Player Characters/Tokens/token_europa_valwater_ai_v2.glb` (only `prototypeToken.flags.levels-3d-preview.model3d` changed from v1; read back OK, everything else identical; the original pre-v1 state is still in `actor_backup_before.json`). v1 (`token_europa_valwater_ai.glb`) is left on the share.
- 14,149 triangles, 1.676 m tall, footprint 0.78 x 0.63 m, base Z=0, centred, facing -Y. Three materials: `Material_0` (SF3D body atlas 2048), `cape` (512x1024, double-sided), `face` (1024 front projection). GLB about 1.1 MB.
- Renders: `europa_v2_turntable.png` (front, 3/4, side, back, other side), `europa_v2_face_closeup.png` (front, 3/4, side of the head), `europa_v2_cape_closeup.png` (side, back 3/4, back).

Steps (run from this folder; Python = `..\..\.venv\Scripts\python.exe`, Blender = `blender -b --factory-startup --python`):
1. `face2d.py --seeds 5,11,23,31`: crops the portrait face, rolls it level (the eye line was 8.9 deg off), upscales it to 1024 and repaints only the eyes with SDXL inpainting (strength 0.75) so they look straight ahead. Seed **11** chosen (`europa_face_11.png`).
2. `ref_v2.py 11`: seed-29 reference with the levelled face pasted into the hood opening and the side cape cut away (`europa_ref_v2.png`, `_rgba.png`). Without the cape in the image, SF3D makes a clean closed body instead of a flat sheet fused to her side.
3. From `foundry-3d`, run `.\ai3d.ps1 -Image ai\characters\europa\europa_ref_v2_rgba.png -Name token_europa_valwater_ai_v2 -Folder "Player Characters/Tokens" -Tris 12000 -Height 1.676`, then `blender\turn180.py`, then `darken.py <in> <out> 0.9 1.2 1.7`.
4. `cape_tex.py`: cape texture (portrait green x1.7, fold shading, gold trim on the sides and hem).
5. `build_v2.py -- geo <dark.glb> <geo.glb> europa_cape_tex.png nocut`: levels the head (pitch/yaw measured from the face normal, falloff over the neck; this run: yaw 9.9 deg, pitch 0) and adds the procedural cape: a 26x44 grid hanging from the shoulder line (z 1.376) to mid-calf (0.36 m), 0.38 m wide at the top widening to 0.66 m, kept just behind the body's back profile so it clears the arms and legs, 5 folds growing toward the hem, the top edge tucked under the hood. (`nocut` skips the v1-only deletion of the old side sheet.)
6. `closeup.py -- <geo.glb> europa_head_front_flat.png emit`: flat front render of the head (0.32 m window).
7. `facecomp.py 11 0.72 0.89 550 550`: lays the levelled portrait face over that render through a soft ellipse, giving `europa_face_tex.png`.
8. `build_v2.py -- face <geo.glb> <final.glb> europa_face_tex.png`: front-facing head faces get the `face` material with planar front UVs in the same window.
9. Copy to `out\Player Characters\Tokens\` and `\\VEGA\varrenmoor-3d\Player Characters\Tokens\`; update the actor's `model3d` through the bridge.

Limits: the head shape itself is SF3D's, and the face is a front projection, so it reads best from the front and 3/4 (from the side the hood hides it). The hands are still SF3D's paler skin. The SF3D back has a yellow-green mantle under the new cape. `analyze.py`, `capesel.py` and the `nocut`-less path of `build_v2.py` are the v1-mesh attempt (deleting the fused sheet left holes in her sleeve), kept for reference. `out/.../token_europa_valwater_ai_v2.blend` is the raw SF3D clean-up stage, not the final.

## v1

Player character Europa Valwater (player PerrottaTheOne), Foundry `Actor.Rugwcr8bm3BirxgK`. The token model is built from her portrait, with the staff and the pangolin removed and her legs set so she stands.

## Result
- Model: `foundry-3d/out/Player Characters/Tokens/token_europa_valwater_ai.glb`, copied to `\\VEGA\varrenmoor-3d\Player Characters\Tokens\`. Foundry path: `assets/varrenmoor-3d/Player Characters/Tokens/token_europa_valwater_ai.glb`.
- 12,000 triangles, one mesh, one material (`Material_0`, metallic 0, roughness 0.85, 2048 base colour and normal maps). Height 1.676 m (5.5 ft), footprint 0.88 x 0.68 m. Base at Z=0, centred, facing Blender -Y, the same as the quest NPC tokens.
- Actor: only `prototypeToken.flags.levels-3d-preview` was set (`model3d`, `scale: 1`, `autoCenter: false`), the same as the quest NPCs. Portrait, token texture, 1x1 size, items, sheet, folder and ownership are unchanged. The original state is saved in `actor_backup_before.json` (`prototypeToken.flags` was `{}`).
- No placed tokens for her existed in any scene on 2026-11-09. Tokens placed from now on get the model. A token placed earlier would have kept the old prototype.
- `europa_turntable.png` shows the model from the front, at 3/4, from the side, from the back and from the other side.

## Pipeline (all on the GPU PC, `foundry-3d/ai/.venv`)
Run from this folder with `..\..\.venv\Scripts\python.exe`:
1. `matte.py`: rembg with the BRIA RMBG weights (`~/.rembg/models/bria-rmbg`) cuts `europa_source.png` out of its background and writes `europa_matte.png`.
2. `prep.py`: hand edits on a 768x1152 canvas, written to `europa_pasteup.png` with the repaint mask `europa_mask.png`:
   - Removes the staff, the top of the staff behind her shoulder, and the pangolin and its tail.
   - Cuts the billowing cape back and repaints it hanging down behind her.
   - Replaces her right hand with a mirrored copy of her relaxed left hand.
   - Replaces the walking back leg with a stretched copy of the front leg.
   - Extends the boots down to the soles, which the portrait crops.
3. `inpaint.py --seq-offload --strength 0.55 --seeds 3,17,29,41,57,73`: SDXL base 1.0 inpainting repaints only the masked seams. Pixels outside the mask are pasted back unchanged, so the face, hood, "E" emblem, gems and tassels are the original pixels. It writes `europa_cand_<seed>.png` and the contact sheet `europa_cands.png`. Each image takes about 30 s with sequential offload.
4. `finalize.py 29`: the chosen seed (29) becomes `europa_ref.png` (plain grey, full body, centred) and `europa_ref_rgba.png` (cut out, the SF3D input).
5. From `foundry-3d`, run `.\ai3d.ps1 -Image ai\characters\europa\europa_ref_rgba.png -Name token_europa_valwater_ai -Folder "Player Characters/Tokens" -Tris 12000 -Height 1.676`. This runs Stable Fast 3D (peak 8 GB VRAM), then `cleanup.py` (decimate, scale, ground, matte material).
6. `blender -b --factory-startup --python blender\turn180.py -- "<glb>"`: SF3D faces +Y, and tokens face -Y.
7. `blender -b --factory-startup --python ai\characters\europa\darken.py -- <in.glb> <out.glb> 0.9 1.2 1.7` (gain, saturation, gamma). SF3D bakes very pale colours, and her grey skin came out near white. This darkens the base colour texture itself. `turn180.py tint=` does not work because glTF export drops its shader node.
8. Copy the GLB to the share folder. Render the views with `blender -b --factory-startup --python ai\characters\europa\turntable.py -- <glb> europa_turntable.png`.
9. Bridge update of the actor, as above.

## Limits and redo notes
- **Pose:** only SDXL base is installed: no ControlNet, OpenPose, IP-Adapter or SDXL inpainting checkpoint. The standing pose was therefore built by hand in `prep.py`, and SDXL only blends the seams. She still has her slightly turned head and upward gaze, and the low camera angle of the portrait. A true re-pose would need `xinsir/controlnet-openpose-sdxl-1.0` (about 2.5 GB fp16) or `thibaud/controlnet-openpose-sdxl-1.0` (about 5 GB), plus an IP-Adapter for identity (`h94/IP-Adapter` sdxl_models, about 1 GB with its image encoder about 2.5 GB). None of these were downloaded.
- **Cape:** the cape is a flat sheet behind her left side, which you can see in the side view. **Back:** the back of the model is SF3D's guess, a cloak in the hood pattern. **Boots:** small gold bits beside the boots come from leftover pangolin-tail pixels that SDXL turned into buckles.
- **Rebuilding:** Foundry caches models by file name. A rebuilt model needs a new file name, or Ctrl+F5 in every client.
- **Undo:** update the actor with `{"prototypeToken.flags.-=levels-3d-preview": null}`, or restore it from `actor_backup_before.json`.
- **Leftover files:** the `.blend` next to the GLB is the clean-up stage, before the turn and the darkening.
