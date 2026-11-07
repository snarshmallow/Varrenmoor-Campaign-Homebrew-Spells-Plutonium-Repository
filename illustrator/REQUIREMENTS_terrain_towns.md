# Requirements: terrain, contours, shading and town generation (user, 2026-11-06)

General rule: towns and features should be natural and flowing, not boxy. Less grid, more grown-over-time layouts. Takes terrain elevation into account, including towns spread over several terrain levels.

## Terrain and contours
- Generate/edit terrain elevation (research diffusion-based terrain and other methods).
- Contour lines with elevation labels; label parameters adjustable (interval, font, size, placement, units, index contours).
- Option to mask contour lines (e.g. hide under buildings/streets).
- Optional terrain shading with phase-based shaders like 3D Canvas: ordered texture "phases", each with an elevation range versus slope-angle rule, sliders to control which phase appears at what elevation/angle, phases re-orderable.

## Plugin GUI (in the Illustrator panel)
- Set up terrain, contours (+ labels), and shading phases with sliders.
- Town generator driven by a **lasso'd area**: generate streets from the selected area; town squares appear for larger areas; blocks/building outlines optional; uses elevation; option to mask contours.
- Textured fills selectable per part (streets, buildings, etc.); ship a few prefilled presets.

## Bridgehollow redesign (all proposed)
- More elevation overall.
- Authority (warden's hall, court, tax office, lockup) in the middle; commoners in a ring around; farms feathered out beyond.
- Mountains steep behind (default: north) and on both east and west sides. River and one stone bridge and the Pilgrim Road still need a way in (a pass or valley mouth, default: south or west-south).
- Still: no church, no Gerald/Dunmore Kell/Tobias Wren.

## Landscape diffusion generation (added 2026-11-06)
- A lasso-able area (closed path on a `DIFFUSION AREA` layer, or the selected path) in which a diffusion model generates landscape, with a panel GUI exposing adjustable parameters: prompt, negative prompt, seed, steps, guidance, denoise strength, resolution, style preset, and how strongly the result follows the existing terrain (hillshade/depth conditioning).
- Interpretation (confirm with user): conditioned on the rule-based heightmap + hillshade of the area so the art matches the real contours, output is a painted/textured landscape image placed under the line work and masked to the lasso path (feathered edge option). Optionally also proposes a refined heightmap patch, shown as a preview and accepted or rejected before it changes the terrain.
- Runs locally on the RTX 3080 (10 GB) via the existing AI environment (`foundry-3d/ai`), jobs queued as JSON like other panel actions, results saved versioned under `illustrator/out/` and logged with their parameters so any result can be reproduced.

## Terrain patch tool (clarification 2026-11-06, replaces the painted-art reading above as the primary meaning)
Lasso an area and set: max height, average height, steepness, and terrain type (e.g. mountain, rolling hills, mesa, dunes, rocky crags, plateau). The highest points sit at the centre of the lassoed area; the edges blend/feather to match the surrounding terrain. Result modifies the heightmap (preview, accept/reject, undo history), then contours, shading and town generation all use it. Diffusion-model art generation stays as an optional later extra.
