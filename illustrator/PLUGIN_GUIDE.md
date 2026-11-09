# Varrenmoor Illustrator plugin and Foundry bridge: GM guide

Plain-language guide for the GM. No programming needed. It covers the Illustrator panel ("Varrenmoor Bridge"), the relay that connects it to Foundry, and the order in which to do things.

Everything here was checked against the panel's HTML, the generator code and the notes in `illustrator/out/`. Where I could not confirm a control or a number, the guide says **check in panel**. Things that were only tested offline are listed in section 8.

Contents: 1 What it is and the daily workflow, 2 Tab-by-tab reference, 3 Foundry bridge, 4 After any models push, 5 Blender, 6 Performance, 7 Troubleshooting, 8 Not yet live-tested, 9 Private-use note.

---

## 1. What it is, and the daily workflow

### 1.1 The two PCs

| PC | Role | What runs there |
|---|---|---|
| Illustrator / GPU PC | Where you work | Illustrator with the Varrenmoor panel, the Python generators in `illustrator/generators/`, optionally Blender and Claude |
| Foundry PC (always on) | Where the game lives | The Foundry server, a GM browser tab, the **relay** (the bridge between the panel and Foundry) |

The panel talks to Foundry through the relay. The relay waits for the Foundry module in a GM browser tab and forwards the panel's requests to it. If the relay is not running, or no GM tab is open, nothing can be pushed.

### 1.2 Vocabulary

| Word | Meaning |
|---|---|
| Place | A folder `world/<id>/` holding terrain, rivers, streets, districts and buildings. The **Place** dropdown at the top of the panel chooses which place every tab works on. |
| View | The text box next to Place: `town`, `bowl`, `street:<id>` or `building:<id>`. It decides what the map frames. |
| World pack | The 3D export of a place (`world/<place>/export/`): terrain, roads, buildings, water as models. |
| Split models | One 3D model file (GLB) per layer or building, plus `placements.json`. |
| Merge | Combines the split models into fewer, bigger files so Foundry draws fewer things. |
| Push | Sends something to Foundry. Everything the pipeline creates carries a hidden flag, so a second push **updates in place** and never makes a duplicate. |
| Padding | The distant ground and horizon around the 3D map ("table" heightmap, apron mesh, ground texture). |
| Skybox | The horizon picture around the 3D scene, generated from the place's real mountains. |
| Proposed / generated | Everything the generators create is a draft, not canon. Edit it freely. |

### 1.3 The daily workflow in 10 steps

Steps 1 to 6 happen on the Illustrator PC in the panel. Steps 7 and 8 push to Foundry. Step 9 is the check. Step 10 is housekeeping.

1. **Make or choose the place.** Places tab: either describe a new place (template, plain words, or the form) and press **Generate place**, or **Import scene as place** from an existing Foundry scene. Or just pick an existing place in the top dropdown.
2. **Set the area, districts and streets.** Town tab: capture or auto-fit the lasso, press **Generate**, look at the result, then **Accept** (or **Reject**). Water and Terrain tabs come first if the land itself needs changing. Regions tab makes zoomed-in child maps of a district.
3. **Pick building styles.** Buildings tab: choose a look (Tudor, Danish half-timber, brick and so on), choose what it applies to (selected, a kind, a district, all), press **Apply style**.
4. **Bridges.** Bridges tab: **Detect**, choose a style for each crossing, **Apply to selected**; or **Auto-fix all crossings**. (Places without gullies, rivers crossing roads or road-over-road crossings show an empty list. That is normal.)
5. **Foliage.** Foliage tab: pick a species mix, set density and area, **Scatter**. Check **Counts** and **Preview render**.
6. **Surroundings and sky.** Padding tab (distant ground) and Skybox tab (horizon image). You can prepare both now, but they only reach Foundry in step 8 and again after every model push (section 4).
7. **Export the 3D pack.** Foundry tab, "3D models" block: **Export world pack (3D)**, then **Export split models**. Set the Roads (3D) block first if roads look wrong. Then **Merge/compress** (optional, recommended for big scenes).
8. **Push to Foundry.** Foundry tab, top: confirm the bridge is connected (section 3). Choose the target scene (New scene by name, or Existing scene). Then:
   - **2D flat map:** **Export view**, then **Push scene** (or **Push tiles** for scene plus a transparent overlay of label layers).
   - **3D scene:** **Push models** (or **Publish (merge + push)** which does merge and push in one go). Foliage has its own **Publish to Foundry** button in the Foliage tab.
   - Right after a models push: Padding tab **Push to Foundry scene**, then Skybox tab **Apply to scene** (section 4).
9. **Check in Foundry.** In the GM tab press **Ctrl+F5** (the browser caches models by path), then look at the scene from above and at street level. Roads continuous, no black band at the edge, sky visible, no missing tiles, clean console (F12). In 3D, cast shadows only show when the Foundry client setting `shadowQuality` is above 0.
10. **Tidy up.** Layers tab: lock guides, clear stale marks. Dry-run settings stay on by default for risky writes (skybox and padding), so nothing changes in Foundry until you untick the dry-run box.

Quick rules of thumb:

- Press **Preview** or **Dry run** first for anything that writes to Foundry.
- One job runs at a time. Press **Cancel** (top bar) to stop a running job.
- Errors show as a red line under the top bar. The **Log** button shows the details.
- Every setting is saved in `world/<place>/panel_state.json`, so the panel remembers where you were.
- A yellow dot on the Contours, Shading or Town tab means terrain or water changed since that tab last ran. Re-run it. (Layers tab, **Clear stale marks** removes the dots.)

---

## 2. Tab-by-tab reference

The panel has 18 tabs, in this order: Scale, Terrain, Contours, Labels, Shading, Lighting, Skybox, Water, Town, **Buildings** (added next to Town by `styles_ui.js`), **Roads** (added by `objects_ui.js`, single-road editor, see 2.18), Regions, Foliage, Padding, Bridges, Places, Layers, Foundry.

Ranges below come from the panel's own limits. Where a field has no stated sensible value I wrote **check in panel** (the control's tooltip often says more).

### 2.1 Scale

What it does: sets the map scale, grid and page, and regenerates the guide layers (Grid, Scale bar, North arrow, Bounds, NOTES). Your art layers are never touched.

| Control | Meaning | Sensible value |
|---|---|---|
| Preset | town, bowl, street, room: loads a ready-made scale | Start here |
| Scale (ft per inch) | How many feet one inch of page shows | Street maps 20; town maps larger numbers. Use Town tab **Fit scale and centre** to pick a good one |
| Grid (ft) | Grid square size | 5 for street maps (matches the Foundry grid), 10 or more for town |
| Major every | Heavier grid line every N squares | 5 or 10 |
| Page width / height (in) | Artboard size | Match your Illustrator document |
| Units | ft or m | ft (feet are the model unit; this changes only the drawing) |
| Shading dpi | Resolution of rendered shading | 30 to 600; check in panel for the default |
| Link instead of embed | Smaller files; relink after a re-render | Optional |

Buttons: **Apply (regenerate guides)**, **Redraw all GEN layers**, **New document + draw**, **Reload**, **Check images**, relink.

Common mistakes: changing the scale and forgetting to press **Apply**; expecting Scale to change the world (it only changes the drawing).

### 2.2 Terrain

What it does: the base heightmap and hand-made "patches" (hills, valleys, trenches and so on).

| Control | Meaning | Sensible value |
|---|---|---|
| Seed | Random pattern | Any number; same seed gives the same land |
| Cell (ft) | Size of one heightmap square | 10 for a bowl; smaller is slower |
| Base elevation (ft) | Average height | Whatever your campaign uses |
| Ridge noise amp (ft) | Height of the hills | Tens to a few hundred |
| Noise scale (ft) | Size of the hills | Hundreds of feet |
| Thermal erosion iters | Smoothing of steep slopes | 0 or more; about 60 is the shipped default |
| Smooth sigma (cells) | Blur | About 1 |

Patches: choose a terrain type, set Max height (raise types) or Min height (bowl, valley, trench, sinkhole, seabed shelf), Steepness 0 to 1, Feather (ft), Roughness 0 to 1, Seed, Angle. **Capture polygon** takes the selected closed path in Illustrator (or the path on layer TERRAIN AREA). **Preview** shows a hillshade and changes nothing. **Apply** saves it. Undo and Redo work.

Common mistakes:

- **Generate base terrain** (red button) regenerates the base and replays the patches. It rewrites the heightmap, so use it deliberately.
- Capturing with nothing selected (the tag next to the button still says "none").
- After any terrain change, re-run Contours, Shading and Town (yellow dots remind you).

### 2.3 Contours

What it does: contour lines and elevation labels from the current terrain.

Key fields: Minor interval and Index interval (the heavier line; the index should be a multiple of the minor), Units, Label size (pt), Decimals (0 to 3), Label spacing (ft, 50 or more), Min length (ft). Checkboxes: labels, along-line rotation, upright flip, emphasise datum, casing under contours, mask under buildings and streets.

Press **Render contours**. It draws Contours - Minor, Contours - Index and Labels - Elevation.

Common mistake: a minor interval too small for the scale makes a black mess. Make it larger or raise Min length.

### 2.4 Labels

What it does: how labels look and where they go. Label text, halo (outline), backing box and knock-out (cutting lines beneath the text) are set per category (All, Districts and plazas, Streets, Buildings, Rooms, Elevation). "All" is the base; category rows only store what you change.

Sections:

- **Label style:** font, size (blank = automatic), letter spacing, case, colour, bold, italic, auto-contrast.
- **Wrapping:** off, auto (fit the shape) or max width; lines, alignment, break style, abbreviations (list in `presets/label_abbreviations.json`).
- **Halo / backing / knock-out:** mode none, halo stroke, backing box or mask. Opacity fields are 0 to 1.
- **Leaders:** lines from a label to its anchor when the label does not fit.
- **Move labels by hand:** drag the label text with the Selection tool (not the leader line). **Re-route leaders** rebuilds the leader lines; **Pin label positions** saves your moves so a redraw keeps them; **Clear overrides** lets the generator place labels again.
- **Declutter:** Preset, plus what to do when a label finds no free spot (hide it, number it with a legend, or keep it overlapping). The tier table sets, for Districts, Plazas, Civic/trade, Streets and Houses/farms, the largest view scale (ft per inch) at which that tier is shown.

Press **Redraw labels only** after changes.

Common mistakes: hand-moving the leader line instead of the text; forgetting to **Pin** before redrawing (moves are lost); labels missing because the view scale is above a tier's limit (they are hidden, not deleted, in LABELS / Labels - Hidden).

### 2.5 Shading

What it does: paints the terrain colours as an image placed on ART - Shading (below the line work, locked).

Controls: Preset (for example temperate_valley, alpine_steep, dry_hills, coastal_basin, parchment, ink_wash, town_winter; the "_calm" versions are muted), Base colour, phases (each with elevation and slope ranges, blends, opacity, jitter, which you can drag to reorder), Hillshade (azimuth, altitude, strength, ambient), Muted settings (saturation 0 to 1, contrast 0 to 1, tint colour and amount, slope smoothing in ft).

Sliders have a number box beside them. Values: elevation ft step 1, slopes 1 to 90 degrees, blends 0 to 200 ft or 0 to 30 degrees, opacity 0 to 1.

Press **Render and place on ART - Shading**.

Common mistake: raising shading dpi on a huge map; it renders slowly. Keep it modest and use the Preview first.

### 2.6 Lighting

What it does: sun direction and cast shadows on the 2D map, and lights that can later be pushed to Foundry.

Key fields: Enabled, Lights (sun and placed lights, sun only, placed only), Sun azimuth (degrees clockwise from north), Sun altitude (degrees), Softness, Intensity, Colour; placed lights (**+ Lantern**, **+ Torch**, **+ Bonfire**, **+ Beacon**, then **Capture point** with a point selected in Illustrator); Shadows (opacity, colour, blur ft, max length ft, ambient 0 dark to 1, slope shading, building height scale, gable roofs, terrain/building shadows, light glow); Output (editable vector building shadows, auto re-render, Preview dpi, Full dpi).

Buttons: **Preview (low dpi)**, **Render shadows**, **Remove images**.

Tips: set the blend mode of ART - Shadows to Multiply and ART - Light Glow to Screen or Soft Light in Illustrator. Building heights come from `presets/building_heights.json`.

Common mistake: expecting placed lights to become Foundry lights automatically from the map. House lights from interior layouts are pushed with **Push interior lights** (Foundry tab; `foundry_push.py push-lights`), and thinned or switched to ambient light with the block in 2.6.1. Lights listed in `placements.json` are not turned into Foundry light documents by the panel (check in panel / see section 8).

#### 2.6.1 Foundry 3D lighting and light budget (Lighting tab, last block)

What it does: controls how many lights the Foundry 3D scene has and how it is lit, so a large map does not drown the GPU. Works on the existing scene picked on the Foundry tab; the command is `foundry_push.py set-lighting` (dry run by default). Only the pipeline's own lights (flags.varrenmoor.pipelineId `light:*`) are touched; lights you placed by hand in Foundry are left alone.

Why it matters (measured on the Dyers Walk test scene, 1858x937, see FOUNDRY_3D_CANVAS_NOTES.md section 11): every visible point light is evaluated for every pixel, so GPU time per frame went from about 6 ms (no point lights or up to about 16) to about 8 ms (36 lights) and about 14-15 ms (72 lights). A light that casts shadows is far worse (4 shadow lights halved the frame rate). Ambient light ("global illumination") and the sun cost the same at any light count.

Key fields: **Lighting mode** (Auto by light count, Point lights all, Hybrid few lights + ambient, Global illumination only), **Max lights** (slider + number box, 0 = no limit; most important kept first: plazas, street lamps, doors, hearths, windows; the rest are thinned by distance so survivors are spread out), **Light radius** and **Light strength** multipliers (from the original values, never compounding), **Interior hearth lights** / **Window lights** checkboxes, **Light shadows** (leave, off, 4 or 8 most important, every kept light), **3D point lights** (scene flag renderSceneLights), and a tick box **Also set sun, ambient and time of day** that enables **Time of day** (dawn / noon / dusk / night), **Ambient (global illumination)** strength and colour, **Sun strength** and colour.

Buttons: **Performance mode** (hybrid, 12 lights, no windows, no light shadows), **Reset to defaults**, **Check (dry run)** (reads the scene, writes nothing, fills the readout), **Apply to scene**. The readout shows the light count in the scene and in the pack by kind, the plan (how many on / off and why, for example "auto: 300 lights is more than 256, so global illumination is used instead of point lights"), the estimated relative cost (1.0 = a scene with only sun and ambient; low / medium / high / very high) and the result of the last check or apply.

Defaults: mode Auto, no limit, scale 1, shadows and flags untouched. Auto keeps every light up to 64 lights (so small scenes are exactly as before), keeps the 16 most important between 65 and 150 and raises the ambient to at least 0.45 (hybrid), and uses ambient + sun only above 150 (ambient at least 0.55). Over-budget lights are hidden, not deleted: raise the budget or switch to Point lights and Apply to bring them back. **Push interior lights** and the Tools tab one-shot 3D scene push use the same mode and budget (lights over budget are not created, and pruned if present).

Cost, limits, unverified: the cost number is a guide measured on one GPU. Light shadows need the Foundry client setting "3D Canvas shadow quality" above 0, which is per browser and cannot be set from here. There is no Foundry scene flag for shadow quality or a light cap; these are client settings.

### 2.7 Skybox

What it does: makes a horizon picture from this place's real terrain (the mountains on the horizon are the real ones), and applies it to a Foundry scene.

| Control | Meaning | Sensible value |
|---|---|---|
| Preset | clear_day, overcast, dusk, winter, night (and any "Imported: ..." sky) | clear_day |
| Image width | 1024 px (fast), 2048 px, 4096 px (slow, large) | 2048 |
| Turn sky (degrees, -180 to 180) | Rotates the picture clockwise seen from above | 0; use only if the mountains sit in the wrong direction in 3D |
| Viewer x,y (ft) | Where the horizon is viewed from | Blank = map middle |
| Sun follows Lighting tab | Draws the sun where the Lighting tab says | On |

Buttons: **Regenerate**, **Rescan**.

Apply to scene: **Refresh scenes**, pick a scene or paste its uuid (`Scene.xxxx`), keep **Dry run** ticked first (it only prints the flags), then untick it and press **Apply**. It writes only the sky and, if ticked, the sun flags of the scene you named.

Import a sky from an existing scene: pick the scene, optionally name it, press **Import sky from scene**. Read-only on Foundry. The new sky appears in the Preset list. Skies with six separate images (cube) or EXR/HDR files cannot be imported.

Common mistakes: forgetting that **Push models resets the sky** (section 4); applying with Dry run still ticked and wondering why nothing changed.

### 2.8 Water

What it does: derives rivers from the terrain, carves them, adds rivers and lakes by hand, and reports bridge crossings.

| Control | Meaning |
|---|---|
| Sea level (ft) | Height of the sea |
| River threshold (cells) | How big a catchment must be to count as a river |
| Outlet width, Bank (ft) | Mouth width and bank size |
| Off-map inflow lines | One per line: `x,y,acres` |
| Delta, Meander, Use derived water, Use carved terrain | Toggles (they decide what every generator reads) |

Buttons: **Derive rivers**, **Carve rivers**, **Bridges report**, **Regenerate river + terrain** (meander preset straight, gentle or lazy; amplitude, wavelength, width variation, seed, sandbar hints). Add river: capture an open path, then name, width, end width, depth, flow, meander. Add lake: capture a closed path, then kind (pond or lake), level, max depth.

Common mistakes:

- **Regenerate river + terrain** rewrites the terrain. Re-run the Town afterwards, and Refresh child regions from their parent.
- Adding a river without capturing a path first.

**3D water in Foundry** (group at the bottom of the Water tab): what it does: makes the water in the 3D scene move. A river flows along its channel (faster where the bed is steeper), ponds and lakes ripple and drift with the wind, the ocean rolls in long swells with foam. Pick a **Preset** (River, Pond, Lake, Ocean), then tune it. The sliders and their value boxes are saved with the place.

| Control | Meaning |
|---|---|
| Preset | Which preset the sliders show and edit. Each water body uses the preset of its own kind (river and stream = River, pond = Pond, lake = Lake, sea = Ocean) |
| Use this preset for all water in this place | Overrides the kinds: every water body takes the shown preset |
| Flow speed (0-4 ft/s) | How fast the ripples drift (river: along the channel, scaled by the slope; others: along the wind) |
| Wave height (0-2) | How strongly the waves tilt the surface (sun glints, dimples) |
| Wave scale (0.25-10) | Ripple size, 1 is about 4 ft crest to crest; lakes 3, ocean 8 |
| Transparency (0-1) | 0 nearly opaque, 1 clear; always clearer at the banks |
| Depth tint (0-1) | How much darker and bluer it gets away from the bank |
| Foam (0-1) | White foam at the shore; on the ocean also on the wave crests |
| Wind direction (deg) | Compass bearing the wind blows toward (0 north, 90 east); a river ignores it |
| Slope speed-up (0-1) | How much steeper stretches of a river speed up the flow |
| Shallow / Deep colour | The two water colours |
| Foundry scene, Dry run | Where to push; Dry run (on by default) only lists what would change |

Buttons: **Refresh scenes** (read-only), **Install on scene** (writes the water shader and these settings into every water tile of that scene; safe to repeat; also switches the scene's animation scripts on if they are off), **Push values** (changes the settings on the scene live, the water tile reloads once). A fresh **Push models** or **Push scene 3D** already puts the script and your saved values on the water tiles, and the export names the water material `VB_water_<preset>` and writes the flow data the shader needs, so re-export after changing a place's water, not after moving a slider.

Common mistakes: forgetting to untick Dry run; expecting the 2D map to move (only the 3D scene does); changing sliders and not pressing **Push values** (the scene keeps the old values until then).

### 2.9 Town

What it does: generates districts, streets, plazas, blocks, buildings and fields inside a lasso that follows buildable ground.

Order:

1. **Capture lasso** (selected closed path or the path on TOWN AREA), or **Auto lasso from terrain** (Slope limit, River buffer, Smoothing, Min width, Edge wobble, Target area, Area seed, Area scale), or **Smooth/snap my lasso**.
2. **Frame the page:** **Fit scale and centre** picks the next nice scale so the built-up area fills the page.
3. Set Seed, Detail (1 to 3), Entry x,y, Plaza min area, Max street grade, Max main grade, Max build slope, Max build relief, Max field slope and the checkboxes (Plazas, Blocks, Buildings, Fields, Contour mask, Redraw contours). Rings set radius, street width and lot area from centre outward.
4. **Generate.** It writes a candidate and draws it; your saved world model is untouched. Then **Accept** to keep it or **Reject** to throw it away. "Export world pack (3D) after Accept" is optional.

Map fills: **Render map with fills** (textured, chosen by feature type; Fill dpi) or the older flat fills (**Apply flat fills now**, with a style preset).

Common mistakes: forgetting **Accept**; pressing Generate on a hand-edited town (it generates a fresh candidate, so compare before accepting); a lasso that is too small gives few buildings.

### 2.10 Buildings

What it does: gives buildings a 3D look. 25 styles: houses (tudor, danish_fachwerk, falu_cottage, hanseatic_brick, niedersachsen_halle, danish_longhouse, norse_log, tarred_timber), town buildings (inn, shop, smithy, warehouse, mill, barn, guildhall, watchhouse, gatehouse), churches (chapel, parish_church, stave_church) and others (boathouse, well_house, windmill, watermill, farm_longhouse).

How to use: pick a style in the gallery or dropdown, choose **Apply to** (ticked buildings, a kind, a district, or all; "Use Illustrator selection" reads the selected shapes' names), press **Apply style**. **Auto by kind + district** picks sensible looks; **Clear style** returns to the old look.

The style is stored in each building's file. It only shows in 3D after you export the world pack and split models again (step 7).

Common mistakes: expecting the 2D map to change (it does not); forgetting to re-export. Gatehouses have a carriage arch and no door. The rose window on a parish church is a real opening; try `special.rose.foil` of `trefoil` or `quatrefoil` in the preset only if you edit presets (see section 8).

### 2.11 Regions

What it does: makes a zoomed-in child map of a district (same feet and ids, larger scale, optional generated detail) and can push it as its own Foundry scene.

Steps: choose the region (District / ring / field from the model, a Lasso, or a Rectangle in feet), give it a Name and Margin, press **Preview extent**, choose Target scale (Feet per inch, Grid ft, Terrain cell ft, contour intervals), tick the details you want (doors, roofs, chimneys, lots, fences, kerbs/sidewalks, trees), then **Create region map**.

Existing children: **Refresh from parent** (your hand edits and ART layers are kept), **Sync back (diff)** (shows differences only; writes nothing) and **Apply diff to parent...**.

Foundry block: grid px per square, export dpi, scene name, parent scene name, **Dry run push**, **Push region scene to Foundry** (needs the child map open and active in Illustrator), **Link on parent scene** (tick "Really write the outline link" or it is a dry run).

Common mistakes: building a region before the parent town is final; pushing without the child map open; leaving "Test copy" ticked (it writes to `world/_region_test` instead).

### 2.12 Foliage

What it does: scatters trees, shrubs and ground cover, draws 2D symbols and prepares 3D models.

Tree crowns and LOD (fix 2026-11): the far LOD 2 impostor cards used to cut off the tops (and sides) of crowns, because the painted tile ran past its edge and the card was only as tall as the nominal height while the real crown overshoots it. Impostor tiles now keep a margin and each card is sized from the LOD 0 crown bounds (test_foliage_crowns.py). Re-run `foliage.py merge` (or the pack export) to rewrite the atlas and chunk GLBs of an existing place.

Scatter rules:

| Control | Meaning | Sensible value |
|---|---|---|
| Mix preset | northern_mixed_forest, pine_heath, spruce_forest, birch_grove, oak_beech_wood, riverbank, village_green, orchard, garden_edge | Match the climate |
| Pattern | How to place (uniform, cluster, rows, lines and so on) | check in panel |
| Zone id | Name of this batch; regenerating a zone replaces only its generated trees | z1, z2... |
| Density per hectare | Trees per hectare, all species | 200 is the default; start lower in towns |
| Size variation 0 to 1 | | 0.5 |
| Max slope (deg), Elevation min/max (ft) | Where trees may grow | check in panel |
| Moisture bias -1 to 1 | Positive favours wet species | 0 |
| Avoid buildings / roads / water | Keep-outs | On |

Area: captured lasso, Town tab area, a district, or the whole place. **Scatter**, **Clear area** (hand-placed trees stay unless "also hand-placed" is ticked), **Add at selection** for a single tree, **Counts**, **Preview render**, **Redraw 2D symbols**.

Merge for performance (3D): see section 6. Presets are Balanced, Performance, Low-end GPU and Quality. **Merge**, **Publish (dry run)**, **Publish to Foundry** (needs the Foundry scene uuid).

Foliage stands on the final graded terrain and skips road beds, bridge decks and building footprints.

Imported (Baileywiki) species join climate mixes automatically when `third_party/baileywiki` exists and are skipped when it does not (section 9).

Common mistakes: publishing 3D foliage without merging (thousands of separate tiles, see section 6); scattering on the whole place when you only wanted the park; expecting trees to appear in 3D before you export and publish.

### 2.13 Padding

What it does: builds the distant ground around the 3D map so the edge does not end in a black table.

| Control | Meaning | Sensible value |
|---|---|---|
| Height preset | bowl-ridge, coastal-flats, fjord-walls, flat-plain, rolling-hills, none | bowl-ridge for Bridgehollow |
| Texture preset | Ground colours | Default |
| Blend / apron width (ft) | Feathered ring from the terrain edge to the table | 200 |
| Relief fades in over (ft) | The table stays flat under the apron, then relief rises | 500 |
| Height scale (x) | Vertical multiplier of distant relief | 1 |
| Seed | | 7 |
| Table plane (ft) | Blank = automatic | Auto |
| Apron mesh | Seamless edge | On |
| Preset overrides (JSON) | Example: `{"ridge_amp_ft": 200, "rise_ft": 40}` | Leave blank unless needed |

Buttons: **Generate + preview**, **Dry run push**, **Push to Foundry scene** (uses the Dry run checkbox, which starts ticked), **Save as preset**. Optional **Set scene padding** fraction (blank keeps what the scene has).

The scene needs the 3D model tiles pushed first.

Common mistakes: pushing padding before the models (nothing to attach to); forgetting that **Push models resets the padding** (section 4); leaving Dry run ticked.

### 2.14 Bridges

What it does: finds places where a road floats over a gully, crosses water, or crosses another road, and builds a bridge model there.

Detection thresholds:

| Control | Meaning | Default |
|---|---|---|
| Deck above ground, ft | A deck this high above terrain counts as a bridge | 4 |
| Level difference at a crossing, ft | Height difference between two crossing roads | 3 |

**Detect** lists the crossings. **Auto-fix all crossings** writes `bridges.json`, trims the road ribbons under the decks and re-exports the pack. Hand-tuned bridges are kept.

Selected bridge: Preset, Width (blank = road width), Seed, Clear width/height below (default about 12 and 8 ft), Parapet height, Arches/spans, Arch rise 0.15 (flat) to 0.5 (round), covered bridge supports (pile bents or stone piers), roof (shingle or tile), flower boxes, rope bridge sag (fraction of span, default about 0.10) and decay (0 sound to 0.5 ruined; default about 0.22).

Presets: stone_arch, brick_arch, flat_cut_stone, wooden_truss, plank_footbridge, rough_log, covered_timber, rope_plank. Check in panel: the panel may suggest a style by road class; your manual choice overrides it.

Buttons: **Preview render** (needs Blender), **Apply to selected**, **Remove**, **Zoom to it**.

Common mistakes:

- A rough log longer than its limit needs trestles (handled automatically up to about 70 ft). A very long span may report `ok: false`; try a different preset.
- Expecting the terrain to be cut: it is lifted and ramped, not cut, unless auto carving triggers.
- After applying bridges you must re-export, split, merge and push (steps 7 to 8).

### 2.15 Places

What it does: lists, creates and imports places.

**Places table:** **Switch to selected**, **Preview selected** (headless PNG, no Illustrator needed), **Open selected in Illustrator** (small places only).

**New place:**

1. Pick a **Template** (coastal fishing village, river market town, mountain pass fort-town, walled hill town, farming hamlet) and **Load template into form**, or type plain words, for example `walled coastal town of 800 people with a big river, Danish style, hilly`, and **Fill form from words**. This is a keyword parser, not understanding: it tells you which words it ignored. For nuance, ask Claude to write a spec (see `illustrator/PLACES.md`) and paste it under "Paste a spec".
2. Check the form: Name, Id, Culture (generic fantasy, Scandinavian, Danish/North German, English), Population, Layout (organic, radial, grid, linear, walled), Centre feature (market, green, temple, castle, none), Terrain (flat, rolling, hills, valley, bowl, coastal, island, pass, fjord, mountain), Sea side, Rivers (0 to 3), River bends, Lakes, Relief, Climate, Season, Width, Height, Seed, Town wall and gates.
3. **Validate**, then **Generate place**. **Regenerate (overwrite)** replaces `world/<id>` (hand edits are lost).

Important checkboxes: **Draft quality** (default on: coarse terrain, civic buildings only, in seconds, safe to open); **Allow large** (lifts the size caps; slow, memory-hungry); Render a preview PNG; Also write the Illustrator job.

Limits to remember: a "grid" town is grid-leaning, not a ruled lattice; on a narrow pass or very steep site the market square may not fit; the town wall appears in the 2D map and `walls.json` but is not in the 3D export unless you inject it (section 8); very large towns can take minutes.

**Import a Foundry scene as a place** (read-only on Foundry): pick the scene or paste its uuid, choose whether closed wall loops become building outlines, tick the extras (lights, tokens, notes), **Check (dry run)** then **Import scene as place**. You get the scale from the scene grid, the background image as an underlay, walls as lines and building outlines. No terrain (a flat stub), streets or water. The place remembers its scene, so a later push goes back to it.

### 2.16 Layers

Small housekeeping tab: **Lock GUIDES / Unlock GUIDES**, **Show LABELS / Hide LABELS**, **Regenerate view (guides)**, **Redraw all GEN layers**, **Open out folder**, **Clear stale marks**, **Open job log folder**.

### 2.17 Foundry

This is the busiest tab. Top to bottom:

1. **Bridge relay and pairing** (section 3).
2. **Place and target:** Target is New scene (create) with a name, or Existing scene (**Refresh from Foundry** to fill the list). **Check connection** tests the link. **Import scene as place** is a shortcut to the Places import.
3. **Scene (2D):**

   | Control | Meaning | Sensible value |
   |---|---|---|
   | Export dpi | Resolution of the exported map PNG | check in panel; Foundry's image limit is 8192 px |
   | Feet per grid square | Blank = the view's grid | Leave blank |
   | Walls from buildings / Road drawings / Water drawings | What to create in the scene | Walls on |
   | Overlay tile layers | For **Push tiles** | Optional |

   Buttons: **Export view**, **Push scene** (flat 2D scene: background image, calibrated grid, walls), **Push tiles**, **Auto-push on save** (off by default; leave it off unless you want every save to push).
4. **3D models:**

   | Control | Meaning | Sensible value |
   |---|---|---|
   | Split | Which layers are one file per entity, group or layer | e.g. `buildings=entity,roads=layer` |
   | Merge preset | by layer, by district, all, keep individual | by layer for the town view |
   | Layers to push | Blank = all | Use a list (for example `terrain,buildings,roads`) to push only some |
   | LOD | 0 full, 1, 2 | 0 |
   | Roof mode | None: roofs merged into each building (default, cheapest, nothing can be hidden). Per building: every roof is its own tile so you can hide one roof (about one extra tile per building, same triangle count). Per scene: all roofs are one tile (one extra tile, fewer draw calls); hide or show every roof at once; buildings are exported open at the top | None for play, Per scene for a quick look inside, Per building to open single houses. Applies to Export world pack and Export split models, so re-run both after changing it |
   | Roads (3D) Smoothing | 0 follows raw ground, 1 fully smoothed | 0.5 |
   | Roads (3D) Max grade (deg) | Steepest allowed road slope; steeper ground gets a warning and the road is raised clear | 14 |
   | Skirt | Apron down to the ground under raised roads | On |
   | Cut/fill terrain | Reshapes the ground under and beside roads | Off (it changes the terrain mesh; turn on only if roads float badly) |
   | Home interior style | Furnishing and finish of the generated home interiors (needs buildings with doors): Auto (by kind: houses rustic_cottage, farmhouse, townhouses burgher_townhouse, tenements poor_hovel, inns/shops/barns/civic stay plain), Rustic cottage (plank floor, exposed beams and timber posts, timber-framed plaster walls, stone hearth with mantel, trestle table with stools, straw bed, rag rug, hanging herbs and pots), Farmhouse (flagstone floor, lime-washed walls), Burgher townhouse (plastered, canopy bed), Poor hovel (earth floor with straw, rough boards, sparse), Plain (the original look) | Auto |

   Home interior style is recorded by Export world pack (`--interior-style`) and Export split models; changing it needs those two again, then Push models. One building can override the scene: add `"interior_style": "poor_hovel"` (or any style name) to its JSON in `world/<place>/buildings/`, then export again. A styled home costs about 800-1000 more triangles per storey than plain (merged geometry, existing material system, three small new procedural textures). Not yet checked live in Foundry's 3D Canvas.

   Buttons in order: **Export world pack (3D)**, **Export split models**, **Merge/compress**, **Push models**, **Publish (merge + push)**. Roof buttons: **Install roof macros** (once per world: creates the macros "Roofs: toggle all" and "Roofs: toggle selected / at token / pick"; drag them to the Foundry hotbar, for example slots 8 and 9), **Hide roofs** and **Show roofs** (every roof tile of the picked existing scene, no macro needed).

   Roofs in Foundry: a roof tile is hidden with its own Hidden setting, so it is saved with the scene and every player sees it at once; you (GM) still see it as a 50% ghost. "Toggle all" works in both roof modes. "Toggle selected / at token / pick" hides the roof tile you selected, else the roof over your selected token, else shows a list of roofs to tick (in Per scene mode it simply toggles the one roof tile). Changing the roof mode: export again, then Push models; roof tiles of the old mode are removed automatically (a push limited to some layers deletes nothing). Towers and chimneys that rise through the roof belong to the roof tile. LOD 1/2 files of merged buildings are not toggled.
5. **Actors, items, tokens:** filters and pickers, image or spec file (**Browse image**, **Browse spec**), **Place token on scene** (at a building id, street id or x,y feet), **Push actor**, **Push item**. Everything created is flagged, so pushing again updates in place; documents you did not make are only changed after you confirm.

Common mistakes: pushing models to the wrong scene name (a second name makes a second scene); using Push scene for 3D (it is the flat 2D map; Push models is the 3D one: the panel has no 2D/3D mode switch, so check in panel); skipping the re-export after changing buildings or bridges.

---

## 3. The Foundry bridge

### 3.1 How it fits together

```
Illustrator panel  ->  relay (on the Foundry PC, port 3030)  <-  Foundry module in a GM browser tab
```

- The **relay** is a small program (Node.js) on the always-on Foundry PC. It is started with `foundry-bridge\start.bat` (or `bridgectl.mjs start`). Run `start.bat --local` once; the choice is remembered. Allow Node.js on Private networks if Windows Firewall asks.
- The **module** (Varrenmoor Bridge, currently 0.5.1) runs inside a **GM browser tab** on Foundry. A GM client must be open: if no GM tab is open nothing can be pushed.
- Open Foundry as the plain-http LAN address, `http://<foundry-pc>:30000`, **not** an https or Cloudflare address. Pairing is refused on https on purpose.
- The **panel** (Foundry tab, top block) connects to the relay and lets you pair and revoke devices.
- World setting **Allow writes** must be on in Foundry for anything to be created or changed. Pipeline pushes need module 0.3.0 or newer.

### 3.2 Attach mode (the normal way)

In the panel, **Connect** only checks the relay at the address shown and attaches to it. It never starts, stops or restarts anything. The relay address is found automatically (from `client.json`); edit it only if it is wrong. **Find relay** looks for one on this PC and the LAN (read-only).

Rules:

- **Run only one relay.** Two relays confuse both Claude and the module. If a relay on the Foundry PC is running, do not launch one on the Illustrator PC. The panel shows a red "two relays" banner if it sees both.
- **Launch local bridge** (under Advanced) starts a relay on this PC. Use it only if this PC is meant to be the relay.
- **Close bridge** stops only a relay running on this PC, and only if it is `node.exe`. It never touches a relay on another PC.
- The relay window survives closing Illustrator. It does not survive a Windows logoff or reboot (no startup entry is created), so after a reboot of the Foundry PC start the relay again.
- Advanced also holds tokens and diagnostics. You normally never need tokens. Typed tokens stay in memory only and are never saved.

### 3.3 Pairing with the 6-digit code (encrypted)

You do not copy any token by hand.

1. On the Foundry PC, open Foundry as a GM in a browser (`http://<foundry-pc>:30000`). The module looks for the relay on the same host at port 3030. If the relay is on a different PC, type its `host:3030` once in the module setting **Relay address**.
2. The module asks to pair automatically (setting "Ask for pairing automatically", on by default). If it does not, open Module Settings and press **Pair with relay**. It shows a **6-digit code**.
3. In the panel, Foundry tab, **Pairing** block: the same request appears with the same 6 digits and **Approve / Deny** (the relay window also takes A to approve, D to deny). The panel checks for new requests every 2 seconds.
4. **Compare the two codes.** If they are identical, press **Approve** (pick an expiry; the relay window uses 90 days). If they differ, press **Deny**. Never approve without comparing.
5. The module says "paired" and connects. Later connects are automatic.

How it is protected: the handshake is encrypted (X25519 key agreement, ChaCha20-Poly1305), the 6-digit code is derived from both sides' keys, so someone in the middle would show a different code, and later logins use a challenge-response so nothing replayable crosses the network. Pairing works only from private LAN addresses and is refused for anything coming through the Cloudflare tunnel, so players cannot pair.

What is not protected: the rest of the LAN traffic (plain http/ws) is unencrypted after pairing. Keep the relay on your home network and do not pair on a network you do not trust. Full threat model: `foundry-bridge/README.md`.

Other pairing controls (panel, Foundry tab, Pairing): **Turn on / Turn off** pairing and **Auto-request** on/off, with no restart (a relay started by an older script needs one restart first). Requests expire after 2 minutes. Limits per address: 5 requests per 10 minutes, 2 waiting at once, 60 seconds wait after a Deny.

### 3.4 Revoking and rotating

- Paired devices are listed with last seen and expiry. **Revoke** closes that device's connection and deletes its record. The module then forgets the credential, shows one warning and does not retry. Pair again to reconnect.
- **Rotate** gives the device a fresh secret. The relay also rotates automatically in the last 14 days before expiry; the old secret works 5 more minutes.
- Re-pairing the same browser replaces its record, so you should see one device per browser. If the panel flags duplicate devices, revoke the older one.
- If the Foundry PC's browser profile or `foundry-bridge/run/paired-devices.json` is ever exposed, Revoke and re-pair. Treat that file like a password file. It is git-ignored.

### 3.5 If it disconnects

| Check | What to do |
|---|---|
| **Two GM tabs (close code 4002).** The relay keeps only one module connection. A second GM tab takes over and the first shows a single warning ("another GM tab took over"). The panel shows a red warning when it sees repeated `closed 4002` lines. | Close the extra GM tab. Press **F5** in the one you want to take the connection back. |
| Relay window closed or frozen | Reopen it with `start.bat`, or panel **Connect** (attach) if it is still running. The relay window is created so a stray click cannot freeze it (QuickEdit is off). If you opened it by hand in a plain console, a click that starts text selection freezes it; press Esc or Enter. |
| Foundry PC rebooted | Start the relay again, then open the GM tab. |
| Module shows "paired" but no link | Panel **Check connection**. Confirm "Connect to relay" is on in the module settings and that the relay address is right. |
| Panel says the relay is on a different address than `client.json` | Fix the address in the panel and press **Connect**; the block warns when the two differ. |
| Module is too old | Redeploy the module (section 3.6). |
| Window not visible | Hidden mode was chosen. Panel Advanced shows the relay log. |

### 3.6 Updating the module on the Foundry PC

Instructions are in `foundry-bridge/DEPLOY_MODULE.md`. In short, copy the `foundry-bridge/module/varrenmoor-bridge` folder over `<Foundry Data>\modules\varrenmoor-bridge` (keep `relay-url.json` if it exists), then press **Ctrl+F5** in the GM tab and check the version in Add-on Modules. Restart the relay once if the notes say the relay files changed (for 0.5.x). Nothing is pushed to the Foundry PC automatically.

---

## 4. After any models push: re-run padding, then skybox

**Push models (and Publish) resets the scene's table and sky flags to the old template.** You will see a black table edge, streaks, dark rectangles or a missing sky. This is expected, not a bug in the models.

Do this every time, in this order:

1. Padding tab: **Dry run push** to look, then untick **Dry run** and **Push to Foundry scene**.
2. Skybox tab: **Apply to scene** with Dry run unticked.
3. Foundry: **Ctrl+F5**.

(The command-line shortcut `foundry_push.py push-scene-3d` does models, padding and skybox in one go. The panel buttons give you the same result in two clicks.)

Why this order: padding sets the table, heightmap and apron; the skybox is a separate flag that models push also resets. Re-pushing foliage tiles does not reset them.

---

## 5. Blender hand-off

If you want to edit models by hand in Blender (move a house, fix a mesh, add props), use the plain-language guide at **`foundry-3d/BLENDER_GUIDE.md`**. In short: import the world pack, edit (keep each object's origin and name), export the split models back, merge, push. The pack ids are the object names, so edits go back to exactly the right tile in Foundry.

---

## 6. Performance tips for Foundry

The 3D scene is only as fast as the GPU of whoever views it. Start small and add.

### 6.1 Merge your models

- **Merge/compress** with **by layer** reduces draw calls a lot. Measured on the Bridgehollow split (136 buildings, no foliage): 79k triangles, 311 draw calls individually, 19 after merging by layer.
- Use **keep individual** only for buildings you edit or animate.
- For buildings with working doors keep Compression on **none (safest)**. gltfpack changes how door nodes are stored and 3D Canvas probably will not animate those doors (open in section 8). The defaults are safe.
- Compression levels: none (always loads), quant (about half the size; not yet confirmed to load in 3D Canvas, test one file first), meshopt (smallest, may not load in 3D Canvas; do not use unless you have checked).

### 6.2 Merge your foliage

Foliage is the biggest cost. Without merging, every tree is its own tile (the benchmark was about 5,000 draw calls for 3,145 instances). **Merge** groups trees into chunks: one mesh, one material per chunk (about 50 draw calls for the same scene).

| Foliage merge preset | Chunk | Triangle cap | Impostors beyond | Low LOD beyond | Compression |
|---|---|---|---|---|---|
| Balanced (default) | 150 ft | none | off | off | none |
| Performance | 200 ft | 150,000 | 600 ft | 300 ft | quant |
| Low-end GPU | 250 ft | 60,000 | 300 ft | 150 ft | quant |
| Quality | 100 ft | none | off | off | none |

- **Triangle budget** thins the lowest-priority trees first (ground cover first, hand-placed last) until the total fits.
- **Impostors** replace far trees with crossed billboard cards. **Low LOD** swaps in a lighter model.
- v2 trees are about five times heavier than v1 for a far better look: a large forest (3,145 instances) is about 1.1 million triangles uncapped. Use the Performance or Low-end preset for big forests.
- Check the merge report (`foliage_merge_report.json`): `triangle_report` shows which species cost the most, and `lod_warnings` flags heavy hero models (the imported beech is about 30,000 triangles on its own) and scenes above 600k triangles.

### 6.3 Budgets (starting points, not measured on 3D Canvas)

| Item | Target |
|---|---|
| Triangles in view | about 300,000 |
| Draw calls in view | about 150 |
| Texture memory | under 256 MB |
| Single texture size | at most 4096 |

Measure in Foundry (the module has a `perf_sample` op for frame rate while you move a token) and adjust.

### 6.4 Other tips

- Terrain, water and roads: one file per layer.
- Buildings: merge by district for the town view.
- In the GM and player browsers, keep `shadowQuality` at 0 unless you need cast shadows.
- Ctrl+F5 after every rebuild; the browser caches models by path.
- Foundry needs internet for Draco-compressed models, which the pipeline does not produce.
- Foliage and unmerged building tiles can mean thousands of objects. If a scene stutters, merge first, then lower the foliage triangle cap.

---

### 2.17b Click mode (Foundry tab: Install click macros)
Button "Install click macros" runs `foundry_push.py install-click-macros`: creates or updates the world macros "Click mode: roofs and doors (toggle)", "Roofs: toggle all" and "Roofs: toggle selected / at token / pick". Put Click mode on the hotbar, run it once to switch on, again to switch off. While on, a GM click on a roof hides/shows only that roof (per_building scenes, saved) or the whole roof tile (per_scene scenes: all roofs are one node; use per_building for single roofs); a click on a door opens/closes it from any layer. Details and limits: WORLD_PACK.md, Roof modes.

### 2.18 Editing a single building / road

Use this when one building or one road must differ from the rest (a hip roof on one house, a lane that is cobbled and kerbed, a steep road that may cut into the hill). Everything is stored in the place's own files, so it survives re-exports; nothing is written until you press **Apply edits**. A new place has no overrides: the exporter behaves exactly as before.

**One building (Buildings tab, block "Edit selected buildings" under the list)**

1. Choose the building: tick it in the list, or select its shape in Illustrator and press **Use Illustrator selection** (shapes are named `bld_house_041` ...). You can tick several; they all get the same values.
2. Tick the box left of every field you want to change. Unticked fields are never touched. **Load values of first chosen** fills the form from the first building.
3. Fields: Storeys (refused if the building already has a generated interior for a different number of storeys), Interior style, Roof type (gable or hip), Roof pitch, Roof overhang, Roof material, Wall material, No windows (doors stay), Keep as its own model (Merge/compress never merges it into a group, so you can still pick, edit or animate it).
4. A ticked field set to "(default: clear the override)" or an empty number box removes that override. **Reset overrides** removes all of them for the chosen buildings.
5. Press **Apply edits**, then Foundry tab: **Export world pack (3D)**, **Export split models** (and Merge, Push). The 2D map does not change.

Stored as: `floors`, `interior_style` (top-level keys of `world/<place>/buildings/<id>.json`) and an `edit` block (`roof_type, roof_pitch, roof_overhang_ft, roof_material, wall_material, no_windows, keep_individual`). Style presets keep working as before (Apply style); a roof or wall material override beats the style's.

**One road (Roads tab)**

1. Tick the road in the list (bridges cannot be edited here; use the Bridges tab) or select its line in Illustrator (named like `str_008`) and press **Use Illustrator selection**.
2. Tick the fields: Class (road, street, lane, alley: picks the surface style), Width, Surface material, Kerb (yes, no, or as the detail pass decided), and the grading overrides Smoothing, Max grade, Max cross slope and Cut/fill terrain. Grading overrides replace the global "Roads (3D)" values on the Foundry tab for these roads only; Cut/fill works per road (yes cuts only this road, no excludes it even when the global switch is on).
3. **Apply edits**, then export the pack and split models. **Reset overrides** deletes the edit block (the width stays as it is).

Stored as: `geometry.width_ft` (the street's normal width key, so the 2D map follows after a redraw) and an `edit` block on the street in `world/<place>/streets.json` (`class, surface, kerb, grade{smooth,max_grade_deg,cross_deg,cutfill}`). The pack's road entity carries `edit` and `grade_override`.

Command line (same thing the buttons run): `python illustrator/generators/object_edit.py set-building --place P --ids bld_house_041 --set roof_type=hip --set no_windows=true`, `set-road --ids str_008 --set kerb=true --set grade.cutfill=true`, `reset-building`, `reset-road`, `list-buildings`, `list-roads`, `choices`. Values outside the allowed range or unknown textures are refused with a message and nothing is written.

**Road shape: add, reshape, delete, undo (Roads tab, block "Road shape")**

Roads are edited as centrelines (`geometry.points`, feet, y down, the plan coordinates of `streets.json`). The town drawing's Roads layer holds street OUTLINES (closed rings named by the street id); those cannot be read back as a line, so a separate Illustrator layer **Road Centerlines** carries one open path per road, named by its street id (e.g. `str_oak_ring`).

1. **Redraw roads in Illustrator** draws every non-bridge road onto the layer Road Centerlines (the layer is replaced; read your edits first). Page points and feet use the same `panelio.py view` mapping as every other capture (Terrain patch, lights ...), so the paths line up with the town drawing at the current scale and focus.
2. In Illustrator move anchors of those paths, add or delete anchors, or draw new OPEN paths on that layer (any name). Curved segments are flattened to short straight pieces; use Simplify to thin them.
3. Buttons (all keep a backup first; every refusal writes nothing):
   * **Read roads from Illustrator**: the selected open paths, or with nothing selected every open path on Road Centerlines. A path named like a road id reshapes that road; any other path is added as a new road (name, class, width from the boxes).
   * **Add from Illustrator selection**: each selected open path becomes a new road (id `str_<name>`, `_2` ... when taken; several paths get the name plus 1, 2 ...). A path that already carries a road id is refused (use Reshape).
   * **Reshape from Illustrator selection**: selected open paths named by a road id replace that road's line; width, class and edit overrides stay. Unnamed paths, closed paths, bridges and a road selected twice are refused.
   * **Simplify / smooth ticked**: Douglas-Peucker tolerance in feet and/or smoothing passes (endpoints fixed) on the existing line of every ticked road.
   * **Split** (ticked road at a vertex index) and **Join two** (two ticked roads of the same class whose nearest ends are within 25 ft).
   * **Delete ticked roads** (tick "Yes, delete" first). Bridges and roads named in `bridges.json` are refused.
   * **Undo last road change**: restores `streets.json` from the newest backup in `world/<place>/streets_backups/` (one step per press, newest 30 kept). Set / Reset overrides also write a backup, so Undo covers them too.
4. After changes: Foundry tab Export world pack (3D) and split models; redraw the town (Generate town / fills) to refresh the 2D outlines and street labels.

Validation: at least 2 points, length at least 2 ft, finite numbers, points within 2000 ft of the place bounds (a wrong mapping is refused), class road/street/lane/alley, width 2..120 ft, simplify 0..200 ft, smooth 0..50. Changing a road's points deletes its cached per-vertex heights (`elevations_ft`, `elevation_ft`, `grade_max`, `grade_raw_max`, `cut_fill_ft`); the 3D export then samples the terrain along the new line (the road bed is re-derived by the road grading on export; other tools that wrote those heights, e.g. a terrain pass that carved a road bed, must be re-run). Bridges are never changed; a road that ends at a bridge keeps its old end point unless you move it.

Command line: `object_edit.py delete-road --place P --ids a,b`, `add-road --place P --name N --kind lane --width 14 --points "x,y;x,y" [--simplify 1 --smooth 2] [--id str_x]` (or `--points-file F`), `set-road-points --place P --ids a --points ...` (or only `--simplify` / `--smooth` on the existing line), `split-road --ids a --at 3`, `join-roads --ids a,b [--join-tol 25]`, `apply-paths --place P --file paths.json --mode reshape|add|sync` (file `{"paths": [{"name", "points": [[x,y]...], "closed": false}]}` in feet), `draw-roads --place P --view-file view.json --out roads.svg`, `restore-streets --place P`. All take `--dry`. Code: `generators/road_edit.py`; tests `generators/test_object_edit.py` (RoadGeometry) and `panel/test/test_objects_jobs.js`.

Limits: curves are stored as polylines (no Bezier); a road drawn on the Road Centerlines layer keeps its vertices only (handles are flattened); redraw replaces the whole layer; roads are not clipped or snapped to junctions, so draw ends on the road they join; labels, fills and the town outlines follow only after the town is redrawn; the interactive Illustrator round trip was tested with a mock host only.

Not available (no generator support yet): door on/off per building (doors come from the Regions detail pass), per-building storey height (fixed 10 ft), road sidewalks. The full audit of generator features against panel controls is `illustrator/out/panel_coverage.md`.

**More pack options (Foundry tab, 3D models, collapsible)**: split preset, merge compression (quant adds the needed `--allow-quantized` automatically), scene mode flat/3d, carve river beds, conform terrain to roads, prune stale tiles, create roof tiles hidden, **Push models (dry run)**, **Audit scene tiles** (read-only duplicate/stale tile finder), **Lights (dry run)** and **Push interior lights**. Roads (3D) also has Max cross slope and a Road grading on/off switch.


### 2.19 Collision and walls (Foundry tab)
Foundry tab > "More pack options" > "Collision and walls (3D Canvas)": one box per layer for the tile collision flag (defaults: on for ground, roads, buildings, fences, bridges; off for roofs, foliage, water), "Set collision (dry run)" / "Set collision on scene tiles" for the picked existing scene, and boxes per wall layer (Buildings, Walls, Fences, Trees, Water) with "Walls (dry run)" / "Push walls". Push models passes `--collision` only when the boxes differ from the defaults. Walls block sight, sound and light as described in WORLD_PACK.md; the model door and its wall door are opened separately.

### 2.20 Tools tab and command parity
Rule: anything the command line can do has a labelled panel control. The Tools tab (after Foundry) holds what had no home elsewhere. Scene actions use the existing scene picked on the Foundry tab (shown at the top).

- **Result viewer**: every audit and read-only command prints its text into the "Result" box at the top (last run, with time); "Open output folder" opens `illustrator/out` where sheets and JSON go.
- **Audits (read-only)**: Scene tile audit (`foundry_push scene-audit`), Validate world pack / World pack summary / Split pack summary (`worldpack.py validate|info`, `worldpack_split.py info`), Building ground audit (top N, skip mesh), Road height audit (step, exported points or the legacy / graded meshes, smoothing, max grade, cut/fill), Terrain check (minor / index contour), Textures audit (tag, padding only, raw), List places, View export info.
- **Bake ground texture** (`bake-texture`): map image, window in feet or px per foot, paper-margin crop plus dpi, name, format, output folder, tableTex path. "Fill from view" reads the window (and the last exported view image) from the current view. "Bake (local files)" writes only locally; "Bake + publish" copies into the shared assets folder after a confirmation. Apply the result with Push options > Push models (advanced) > Table texture.
- **Push options** (collapsible; they feed the Foundry tab buttons): Push scene 2D (`--upscale --padding --max-px --format --link`), Push models (`--ids --serve-url --assets-dir --px-per-ft --set-name --table-texture --lighting --collision-lod --scene-flag --yes`, and `--yes` for Publish), interior lights (`--light-animation --lighting --lights-placements --prune-lights`), walls (`--wall-profile --foliage-json`), actor portrait / token art, token hidden / key / px, scene import (`--no-image --force --scene-json`).
- **Push whole 3D scene** (`push-scene-3d`): one step for models, foliage, padding (the Padding tab settings by default), lights, skybox, collision. "Push 3D scene (dry run)" plans every step and writes nothing; the real push asks first.
- **Foundry macros**: Install click mode, door sync, roof macros, water shader; Hide / Show roofs; Sync doors (dry run / now).
- **Advanced pack export**: terrain source, LOD steps, style, phases, splat cell, albedo px/ft, px per ft, z origin, pinned timestamp, no textures, split textures and terrain step, merge keep hidden faces, re-export entity ids; padding texture size and level elevation; per-object edit preview (`object_edit --dry`) and list buildings / roads / allowed values.
- **Delete scene**: removes the picked existing scene from Foundry. No dry run exists, so the button stays disabled until you type the scene's exact name (case sensitive), and a second confirmation follows. Afterwards the scene leaves the panel's list.

**Parity test.** `lib/command_manifest.json` lists every command and flag of `foundry_push.py`, `foundry_collision.py`, `foundry_water.py`, `worldpack.py`, `worldpack_split.py`, `object_edit.py`, `padding_heightmap.py`, the audits and `bridgectl.mjs` with the panel control that covers it (`act:` data-act, `s:` state path, `id:`) or a written `cli_only` reason (or `pending`, which the test prints). `node illustrator/panel/test/test_command_parity.js` parses the Python argparse code and fails when a command or flag is missing from the manifest, when a named control does not exist in the panel, or when a manifest entry no longer exists in the code. When you add a flag: add the control, then its manifest line. The Tools tab command lines are covered by `test/test_tools_jobs.js`.

### 2.21 Streetlamps tab (street lamps along the roads)
Toggleable lamp posts on the exported roads: `generators/streetlamps.py` (plan / apply / preview / styles), `generators/streetlamps_scene.py` (`foundry_push.py set-streetlamps`), styles in `presets/streetlamps/styles.json` (thumbnails in `presets/streetlamps/thumbs/`), panel `lib/streetlamps.js` + `streetlamps_ui.js`, tests `generators/test_streetlamps.py` and `panel/test/test_streetlamps_jobs.js`.
* **Styles (6):** wrought-iron post and lantern, wooden post with hanging oil lantern, stone pillar lantern, wall bracket lamp (fixed to the nearest building wall within 14 ft, skipped where there is none), torch post, shepherd's crook lamp. 146 to 416 triangles each, one merged tile for the whole town.
* **Placement:** stations every Spacing ft along each road centreline (centred, 6 ft clear at the ends), Side left / right / alternating / both, Offset ft outside the road edge, Height (0 = style default), classes Main (road, street) / Side (lane, alley) / Dirt (dirt, mud, packed earth, sand surfaces; gravel counts by class). Skipped: near junctions, bridges, exterior doors, inside building footprints; a road that fits fewer than Minimum lamps gets none; Jitter shifts lamps along the road (deterministic per Seed). Lamps stand on the graded road height (the centreline z the road ribbon is built from) with a footing buried 1 ft.
* **Per road:** Roads tab, fields "Street lamps on this road" (yes forces lamps even when the class is off, no = none), style, spacing; written to the street `edit.lamps` {on, style, spacing_ft} (`object_edit.py set-road --set lamps.on=false`).
* **Lights:** one AmbientLight per lamp, kind `lamp` (budget priority 80), colour from Colour temperature (K) or a hex override, dim / bright radius, intensity, Flame flicker (Foundry animation torch), Light shadows off by default (a shadow-casting light costs 6 extra scene passes). 0 in a light box = the style value.
* **Flow:** Preview (dry run) counts lamps and lights and warns against the light budget; Generate writes `models/streetlamps/streetlamps.glb`, a placements entry (layer `streetlamps`: collision on, sight off) and the `lamp` lights into export/placements.json (and the optional extra placements files, e.g. the merged optimized set); with the switch off, Generate removes them again. Push layer + lights then pushes the tile and the pack lights to the picked scene. Show / Hide lamps in scene and Retune lamp lights in scene (`set-streetlamps`, dry run unless the box is unticked) switch the tile and lamp lights on an existing scene without a re-push (lights the budget hid stay hidden).
* CLI: `python illustrator/generators/streetlamps.py apply --place P --pack DIR --enabled on --style wrought_iron --spacing 50 --side both` ; `foundry_push.py set-streetlamps --scene-uuid U --off --apply`.

### 2.22 Sign maker (Tools tab: Install Sign maker; Foundry macro)
Street signs and hanging (tavern / shop) signs as ordinary 3D Canvas tiles whose text you edit inside Foundry.
* Install once: Tools tab > Foundry macros > **Install Sign maker** (or `python illustrator/generators/foundry_push.py install-sign-macro [--dry-run]`). It creates/updates the world macro `Sign maker: street and hanging signs (editable text)` (stable id `macro:sign_maker`; re-running updates it in place). The macro carries the models, the wood and iron textures and the lettering code (about 160 KB), so nothing else is deployed.
* Run it from the Macro directory (GM only). Pick a style by thumbnail: street board on a post, street plaque on a wall, fingerpost with 2, 3 or 4 arms, hanging sign on a wall bracket, hanging sign on a roadside post. Type the text (one line per row; "First line big, others smaller" gives name plus subtitle), pick font, finish (painted, carved, gilt), colour scheme or custom board/ink/trim colours, an icon (mug, anvil, bread, key, boot, barrel, horseshoe, bell, flask, sword, fish, sun) above or left of the text, back side (same, blank, own text), size x0.5-2, letter spacing, weathering, mount height, rotation, texture size. A live preview is drawn in the dialog.
* **Place (click in scene)**: click the ground (post styles) or a WALL (plaque, bracket): the sign turns to face out of the wall and takes the clicked height. **Place at selected token** uses the controlled token or the view centre.
* **Edit**: run the macro again; with a sign tile controlled it opens on that sign, otherwise choose a sign in the "Sign in scene" list (or Pick it in the 3D view), change anything and press **Apply to chosen sign**. The lettering is redrawn and every client sees it after the tile reloads. **Rebuild all signs** repaints every sign of the scene (after changing a font). Delete chosen sign removes the tile.
* Everything about a sign is stored in the tile flag `flags.varrenmoor.sign` (schema in FOUNDRY_3D_CANVAS_NOTES.md section 12). Collision and sight are off, shadows on (tile flag castShadow).
* Limits: GM only (players cannot upload files or create tiles; they do see the signs). Fonts are the ones installed in the GM's browser plus Foundry's own (Modesto Condensed, Amiri, Signika ...); the lettering is a picture, so players need no font. Changing a sign's style needs a new sign (delete the old one). The uploaded files live in the Foundry user data `assets/varrenmoor-signs/` (models, tex, letters); Foundry's API cannot delete files, so removed signs leave their small WebP behind.

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Panel says "relay not checked" or cannot reach Foundry | Relay not running, wrong address, or Foundry PC firewall | On the Foundry PC start the relay (`start.bat`). In the panel **Find relay**, then **Connect**. Allow Node.js on Private networks. |
| Relay running but "module not connected" | No GM tab open, wrong address (https), or module not paired | Open `http://<foundry-pc>:30000` as GM, set **Connect to relay** on, pair (section 3.3) |
| Module bounces between connected and disconnected about once a second | Two GM tabs fighting (close code 4002) | Close the extra GM tab, then F5 in the one you want |
| Pairing code shows in Foundry but not in the panel | Pairing off on the relay, or the panel cannot see the relay | Panel Foundry tab > Pairing > Turn on. Check the relay address and **Connect**. A relay from before 0.5.0 needs one restart. |
| The two codes do not match | Something is in the middle, or two requests are mixed | Press **Deny**. Close the Foundry page, reload, try again. |
| "Module older than 0.3.0" when pushing | Old module on the Foundry PC | Redeploy the module (section 3.6) |
| Writes refused or nothing is created | World setting **Allow writes** is off | Turn it on in the Foundry world settings |
| Push says a scene with that name exists but was not made by the pipeline | You picked **New scene** with the name of one of your own scenes | Choose **Existing scene** and pick it (Refresh from Foundry first), confirm once |
| A push made a duplicate scene | A different scene name was typed | Use the same name or choose **Existing scene**. Delete the extra in Foundry. |
| Black band or black edge at the scene border, streaks, dark rectangles | Push models reset the padding flags | Section 4: Padding push, then Skybox apply |
| No sky or mountains | Skybox flag reset by Push models, or Dry run was left ticked | Skybox tab > untick Dry run > **Apply to scene** |
| Mountains in the wrong direction | Sky orientation | Skybox tab: **Turn sky**, then regenerate and apply |
| Models look old after a push | Browser cache | **Ctrl+F5** in the GM tab |
| Radial colour streaks outward from the edge | Steep apron slope seen from straight above; also an old texture issue now fixed offline | Push padding again, view at an angle; report if still strong (offline fix, check live) |
| Roads cut by terrain or floating | Road grading settings | Foundry tab Roads (3D): raise Smoothing, lower Max grade, or try Cut/fill; re-export split |
| "Road end raised above deck end" or grade warnings in the export log | Ground steeper than the max grade | Informational; read the report. Raise Max grade or accept. |
| Door does not open in 3D | Optimised (gltfpack) GLB hides the door flag | Use Compression none for building layers; click the door; check section 8 |
| Door leaf spins wildly | Old value (degrees read as radians) | Fixed in current generators; re-export and push |
| No bridges listed | The place has no crossing that needs one | Normal (Dyers Walk has none). Lower the thresholds or use a place with a river |
| Bridge style looks wrong or "ok: false" | Span or clearance outside the preset's range | Try another preset in the Bridges tab and Apply |
| Trees do not appear in 3D | Not merged or published, or scene uuid missing | Foliage tab: Merge, then **Publish to Foundry** with the scene uuid |
| Scene is slow after adding trees | Too many separate tree tiles or too many triangles | Merge foliage, use the Performance or Low-end preset, lower the triangle budget |
| Imported (Baileywiki) trees missing | `third_party/baileywiki` is absent | Expected after removal; procedural species still work |
| New place takes forever or Illustrator freezes opening it | Large town in full quality | Use **Draft quality**; do not tick **Allow large** unless needed |
| Place generation says a square did not fit | Narrow pass or steep site | The town still generates; move the entry or relax the terrain |
| Illustrator panel says "no document" yellow warning | No open document | Files are still written; open a document to draw |
| Contours or Shading are marked stale (yellow dot) | Terrain or water changed | Re-run that tab |
| Panel too narrow, tabs wrap or controls clip | Dock width | Panel size is 440 x 720 by default, minimum 300 x 240; restart Illustrator after manifest changes |
| Labels overlap or vanish | Declutter and view scale tiers | Labels tab: adjust the tier table; hidden labels live in LABELS / Labels - Hidden |
| Wrong place edited | Place dropdown | Check the **Place** box at the top before every export or push |

If something is not covered: open the **Log** in the panel and check the red message under the top bar; the job logs are saved in `illustrator/jobs/done/` (use **Open job log folder** on the Layers tab).

---

## 8. What is not yet live-tested

The notes record these as built and tested offline (tests and renders), but not yet confirmed in a live Illustrator or Foundry. Full step-by-step test list: [`illustrator/out/unfinished_work.md`](out/unfinished_work.md).

Highlights:

- 2D and 3D scene push from the panel, and Export view, end to end.
- Regions flow (extract, render, trees not wiped).
- Dragging the panel window wide on every tab (checked only at fixed widths).
- Interior door swing direction (screenshot still to take).
- New bridge presets and fields in a live panel; bridge symbols in an actual 2D render; terrain carving under a bridge on real data (Dyers Walk has no bridges).
- Foliage in 3D Canvas: whether alpha-cut cards, vertex colours and quantised GLBs render correctly, and the frame rate.
- Padding streak fix (seen offline only).
- Rose window and gatehouse carriage arch on a real push.
- Town walls: the 3D wall generator has only been tested on synthetic data; run it by command line, not from the panel.
- Climate mixes with imported trees; new radial and linear layouts on screen.
- Lights in `placements.json` are not turned into Foundry light documents (house lights go through `push-lights`).
- `tableTex` scaling, optimised GLBs with doors, cast-shadow look, and the player view of the padding were not tested live.
- `world/bridgehollow_big` is a local scratch place (not committed); do not use it for 3D export.

Rule for testers: never put credentials in notes; the Foundry GM tab must be signed in by you.

---

## 9. Private-use note: remove third-party assets before any public release

This repository is **private and never distributed**. It includes converted copies of licensed Baileywiki 3D tree models in **`third_party/baileywiki/`**, used as extra foliage species (European beech, ash, young ash, two bushes).

**Before any public release, delete everything in `third_party/` and purge it from git history** (for example `git filter-repo --path third_party --invert-paths`). Instructions are in `third_party/README.md`.

The code is safe to keep: when `third_party/baileywiki` is missing, the imported species are skipped and the procedural foliage still works.

Also keep out of any public copy: `foundry-bridge/.env`, `foundry-bridge/client.json` and `foundry-bridge/run/` (tokens, logs and paired-device secrets; all git-ignored). Never paste a token into a note, chat or file.

---

## Appendix: where things live

| What | Where |
|---|---|
| This guide | `illustrator/PLUGIN_GUIDE.md` |
| Panel source | `illustrator/panel/` (`index.html`, `main.js`, per-tab `*_ui.js`) |
| Generators (Python) | `illustrator/generators/` |
| Places and import | `illustrator/PLACES.md` |
| World pack format and the Blender to Foundry chain | `illustrator/WORLD_PACK.md` |
| How Foundry 3D Canvas renders our pushes | `illustrator/FOUNDRY_3D_CANVAS_NOTES.md` |
| Bridge relay, pairing, security | `foundry-bridge/README.md` |
| Module deployment | `foundry-bridge/DEPLOY_MODULE.md` |
| Blender editing | `foundry-3d/BLENDER_GUIDE.md` |
| Notes per feature | `illustrator/out/*_notes.md` (bridges, building styles, foliage, padding, places, road grade, interiors, panel UI) |
| Live-test checklist | `illustrator/out/unfinished_work.md` |
| Saved panel settings per place | `world/<place>/panel_state.json` |
| Job logs | `illustrator/jobs/done/` |
| Output files (previews, renders) | `illustrator/out/` |

### Lighting tab: Sun, shadows and fog (Foundry 3D)
What it does: makes the 3D Canvas sun read (direction, colour, strength, shadows) and sets fog and sky, with one-click presets. Works on the existing scene picked on the Foundry tab; the command is `foundry_push.py set-sun` (dry run by default). Presets (dawn, morning, noon, afternoon, dusk, night, foggy morning, warm sunset) are editable JSON files in `illustrator/presets/lighting/`; each sets sun azimuth/elevation/colour/strength, ambient, shadow bias, fog and the sky image together.
1. Pick the scene (Foundry tab, Refresh from Foundry). 2. Click a preset (or move the time-of-day slider and the sun sliders; the preview image below updates after a short pause). 3. Check (dry run) lists the scene flags that would change. 4. Apply to scene writes them; "Preview in Foundry (temporary)" is the same write meant for a test scene, and Reset to saved puts the previous flags back (the first apply stores them on the scene). Tick "Build the sky image if missing" the first time you use a preset with its own sky (night, dusk, foggy, sunset): it takes about a minute.
The preview image is an APPROXIMATION made offline (plan view of terrain and building roofs, Lambert light, hard shadows, fog tint, no trees). It is not Foundry's renderer. The panel cannot take a Foundry screenshot.
**IMPORTANT: every player AND the GM must set Configure Settings > 3D Canvas > Shadow Quality to 4 (Medium) once, or they see no sun shadows at all.** The block shows this notice and has an "Install the one-click macro" button (world macro "Set my shadow quality": each person runs it once; players need the Use Script Macros permission). Details: it is a per-browser setting and no scene flag can force it; at 0 nobody sees sun shadows. Keep ambient low (0.05 to 0.15): the sky image already adds fill light and a high ambient flattens the shadows. Fog hides the sky image (3D Canvas shows the flat fog colour), so match the fog colour to the sky horizon. Cost on the Dyers scene: within the noise of 12 ms GPU. "Also write this preset when pushing a 3D scene" makes the Tools tab 3D push pass `--sun-preset`.
CLI: `python illustrator/generators/foundry_push.py set-sun --scene-uuid Scene.X --place P --preset warm_sunset [--make-sky] [--fog on --fog-far 9000] [--apply]`, `--restore --apply` to undo; `python illustrator/generators/sun_preview.py render --place P --preset noon --out x.png`.

**Skies and one shared light direction (dramatic skies).** The lighting presets now include golden_hour, overcast, high_mountain (deep blue, bright sun, snow-capped far ranges) and storm (dark cloud deck, pale tear where the sun sits) next to dawn, morning, noon, afternoon, dusk, night (moon, stars, faint Milky Way), foggy_morning and warm_sunset. The "Sky look" box picks another sky for the same light (clear_day, high_mountain, storm, golden_hour, dusk, overcast, foggy, winter, night). The sun (or the moon, for night skies) in the sky picture is drawn at the same compass bearing and elevation as the sun azimuth/elevation sliders, and the 3D Canvas flags `sunPosition` / `sunTilt` are computed from those same two numbers, so the shadows point away from the sun or moon you see; the preset JSON no longer carries a second `sky.sun_bearing/sun_alt`. Moonlight at night is the same sun rig with a cold colour and low strength. The preview image has a sky strip under the plan (compass 0..360, 5 below to 60 above the horizon) with the sun/moon circled. Fog ON replaces the sky with the flat fog colour in 3D Canvas, so storm, golden_hour, overcast and high_mountain ship with fog off; foggy_morning keeps it on.
Sky images are named `sun_<preset>_<skylook>_az<N>_el<N>.webp` in world/<place>/export/skybox, so changing the azimuth/elevation builds a new image instead of reusing a stale one. Build them without touching Foundry: `python illustrator/generators/skybox.py generate --place P --presets "" --lighting-presets all [--width 2048]` (one image at a time, about 150 MB RAM each), then `set-sun ... --preset storm [--sky-preset golden_hour]` (add `--make-sky` to build on the spot) or `push-scene-3d --sun-preset storm` publishes it. The result of set-sun carries `direction` (sky body bearing/altitude, the light recovered from the flags, error in degrees, must be under 1).
