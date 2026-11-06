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
