# Europa Valwater: 3D token

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
