# Research: terrain, contours, shading, town generation

Context: Illustrator CEP panel (ExtendScript only, job JSON files) plus a Python generator on a Windows PC (RTX 3080 10 GB). World model is JSON in feet, y down (see DESIGN.md). Requirements: REQUIREMENTS_terrain_towns.md.

Verification note: items marked (verified) were seen in search results this session. Items marked (from memory) are well-known but were not re-fetched; check the license file before depending on them. I could not find any documentation of the "phases" feature of 3D Canvas (searches returned only its general module page), so section 4 is a design, not a description of that module.

## 1. Terrain elevation

### ML / diffusion options
| Option | What it is | Local on 3080 10 GB? | License | Notes |
|---|---|---|---|---|
| [xandergos/terrain-diffusion](https://github.com/xandergos/terrain-diffusion) (verified) | Diffusion heightmap generator, sketch to heightmap at about 30 m/px (also 90 m model), HF-hosted weights, README cites a SIGGRAPH '26 paper (InfiniteDiffusion), has an Azgaar-to-TIFF export | Yes, pip + CUDA, inference only | Check repo LICENSE and weight license (not verified) | Closest to a usable sketch-to-terrain tool. Real-Earth statistics, so output is Earth-like, 30 m/px is far coarser than a town (our town is a few thousand ft). Use for the regional mountain/valley backdrop only. |
| [Earthbender (MIG 2025)](https://danial-barazandeh.github.io/Earthbender) (verified) | Stable Diffusion + ControlNet, multi-channel sketch (structure, mountains, lakes, roads/rivers) | Heavy but SD-class models fit 10 GB | No public repo found | Paper only. Shows the approach is feasible. Not usable directly. |
| [TerraFusion, arXiv 2505.04050](https://arxiv.org/pdf/2505.04050) (verified) | Latent diffusion for joint height+texture, sketch control | Unknown | No code found | Paper only. |
| [Interactive Authoring of Terrain using Diffusion Models](https://pubs.cs.uct.ac.za/id/eprint/1583/1/Diffusion%20Terrain.pdf) (verified) | Paper on sketch-guided authoring | n/a | n/a | Reference. |
| [Pixels2Peaks](https://aryamaanjain.github.io/pdf/2026/pixels2peaks.pdf) (verified) | Photo/text/sketch to terrain | n/a | no code found | Paper only. |

Assessment: diffusion terrain is real but immature for this use. The only runnable one is Earth-scale, weights-dependent, hard to steer precisely, and nondeterministic (bad for a persistent world model where "mountains steep on N, E, W; pass to the south" must hold exactly). Treat it as an optional "inspiration" generator that produces a backdrop heightmap the user can import, not the core.

### Classic methods (the core)
- Fractal noise (fBm of OpenSimplex/Perlin; ridged multifractal for sharp ridges; domain warping for organic shapes). Python: `opensimplex` (MIT), `noise`/`pynoise`, or plain numpy FFT noise (1/f^beta spectrum, no dependency, fast, tileable).
- Erosion: thermal erosion (talus angle, easy, vectorizable in numpy) and hydraulic erosion (droplet or grid-based "stream power" with flow accumulation). The grid-based stream power model is what gives branching drainage and believable valleys, and it also gives a river network for free (flow accumulation). Reference implementations: Sebastian Lague's hydraulic erosion (Unity, MIT, from memory), `pyerosion`/various GitHub numpy ports, Axel Paris / Guillaume Cordonnier's "Large Scale Terrain Generation from Tectonic Uplift and Fluvial Erosion" (paper, from memory) for uplift + stream power. For speed use `numba` (`@njit`) on CPU or CuPy/PyTorch on the 3080; a 1024x1024 grid with a few hundred erosion iterations is seconds with numba.
- Interpolation from user-drawn lines: the artist control route. User draws ridge lines, valley lines, and spot heights (and the lasso'd town platform). Solve a smooth surface: Laplace/biharmonic (thin plate) interpolation of constraints (`scipy.sparse.linalg` or `scipy.interpolate.RBFInterpolator` with `thin_plate_spline`), or the "diffusion curves" style. Then add noise detail masked by distance to the constraint curves and erode. This is the Hnaidi et al. "Feature based terrain generation using diffusion equation" idea (from memory) and is also what Gaea/World Machine "ridge + fill" workflows do. Fully deterministic and editable.
- Sketch-to-terrain classic: Guerin et al. "Interactive example-based terrain authoring with conditional GANs" (from memory) is ML; the classic equivalent is the constraint-interpolation approach above.

### Recommendation (item 1)
Core pipeline in Python/numpy (+ numba): user paints/draws control polylines (ridges, valleys, passes, platforms, spot heights) in Illustrator, exported as job JSON; solver builds a base surface by constrained interpolation; add domain-warped ridged fBm detail weighted by "steepness" slider; run thermal then stream-power erosion; carve river along a drawn path and flatten the lasso'd town terraces (blend platforms). Output a float32 .npy/.png (16-bit) heightmap plus `terrain.json` params and seed. Optionally import a terrain-diffusion heightmap as the base layer for the far mountains. Licenses: all of the above are MIT/BSD/numpy-stack permissive; verify terrain-diffusion's weights license before shipping anything derived.

For Bridgehollow: define the heightmap by constraints (N ridge wall, E and W ridge spurs, south valley mouth carved to a notch where the river/Pilgrim Road enters), then noise.

## 2. Contours

- Extraction: marching squares. `skimage.measure.find_contours(h, level)` ([source](https://github.com/scikit-image/scikit-image/blob/v0.14.1/skimage/measure/_find_contours.py), BSD, verified behavior: linear interpolation, returns (row, col) arrays, closed contours repeat first point). Alternative: `contourpy` (MIT, what matplotlib uses; gives closed/open line types and is faster, with optional `LineType.ChunkCombinedOffset`). Pick `contourpy` for speed and correct handling of saddles.
- Pre-smoothing: Gaussian blur the heightmap (sigma 1-2 px) before extraction to kill stair stepping, and upsample (bicubic) 2x for smoother paths. Post-smoothing: Chaikin corner cutting (2 iterations) or fit a Catmull-Rom spline then convert to cubic Beziers; simplify with Douglas-Peucker (`shapely.simplify`, BSD) at about 0.2 px tolerance to keep Illustrator anchor counts low. Avoid smoothing so much contours cross.
- Index contours: every Nth interval (default 5th) gets a heavier stroke and carries the label. Intervals specified in feet or meters; convert heightmap units with a vertical exaggeration/units setting.
- Label placement along contours: algorithm (per index contour, per closed/open path):
  1. Compute arc length, walk with a step (candidate every ~label_spacing).
  2. For each candidate take the tangent over a window the width of the label; reject if curvature (angle change over the window) exceeds about 25 degrees, since labels on tight bends look bad.
  3. Prefer positions where the contour runs roughly horizontally-ish (or uphill-readable): flip text 180 degrees so it is never upside down (as matplotlib's `clabel` does).
  4. Collision check: label rectangle (rotated) as a `shapely` polygon tested against already placed labels, other contour lines (the label breaks its own contour, but should not cross neighboring contours: test the buffered box against other contour geometries), mask polygons (buildings/streets), and page bounds. Use an STRtree.
  5. Gap the line: split the contour path where the label sits (inline label) so the line does not strike through text.
- SVG/Illustrator emission: paths as `<path d="M... C...">`; labels as `<text>` with `transform="rotate(a x y)"`, `text-anchor="middle"`, centered on the point; alternative `<textPath>` on a sub-segment of the contour (nicer, follows curvature, but Illustrator imports textPath less reliably; since our panel builds via ExtendScript, write path points and create `TextFrame` with `rotate`, or an area/path text item from the sub-path). Name items by id (`contour_1250ft`, `lbl_1250ft_03`), put all in `LINES/Terrain` and `LABELS/Elevation`.
- Masking: subtract mask polygons from the contour lines with `shapely` (`line.difference(mask_union)`), which yields broken polylines ready to emit; do not rely on Illustrator clipping so the result is deterministic. Optionally also emit mask as a hidden group.

Recommendation (item 2): numpy heightmap -> Gaussian pre-smooth -> `contourpy` -> shapely simplify + Chaikin -> shapely difference for masks -> label placement with rotated-rectangle STRtree collision -> export as polyline lists in job JSON (anchors only; Catmull-Rom to Bezier done in ExtendScript or Python-supplied handles). Label params (interval, index every N, font, size, units, spacing, min curvature) go in the job.

## 3. Procedural town layout

### Methods
- Parish and Mueller 2001, [Procedural Modeling of Cities](https://doi.org/10.1145/383259.383292) (from memory): extended L-systems growing roads with global goals (population density map, pattern: grid/radial/organic) and local constraints (water, slope, snapping to intersections). Then lot subdivision. Good for growth along terrain; too elaborate to implement fully, but the idea of "road segments with a priority queue and local-constraint repair" is the useful part.
- Chen et al. 2008, [Interactive Procedural Street Modeling](https://www.sci.utah.edu/~chengu/street_sig08/street_project.htm) (verified): tensor fields (basis fields: grid, radial, plus heightmap-derived), streamlines traced along major/minor eigenvectors, which gives organic curved streets that follow the user's field. No official code. Open reimplementations: ProbableTrain's JS "MapGenerator" (MIT, from memory; the repo [ProbableTrain/MapGenerator](https://github.com/ProbableTrain/MapGenerator)), and a Python derivative [panicmod-e/ProceduralCityGenerator](https://github.com/panicmod-e/ProceduralCityGenerator) (verified as based on it; check license). Rust: [symbios-tensor](https://docs.rs/crate/symbios-tensor/0.1.0) (MIT, verified) derives road directions from heightmaps. The tensor approach is the best fit: the field can be seeded from terrain contours, so streets run along contours and cross them at switchbacks.
- Watabou's Medieval Fantasy City Generator: source [watabou/TownGeneratorOS](https://github.com/watabou/TownGeneratorOS) (verified), Haxe, **GPL-3.0** (per Ecosyste.ms index; verified secondhand), older than the web version. Method (from memory): Voronoi of jittered points, central cell becomes plaza, wards assigned (market, craftsmen, patriciate, slum, gate wards...), city wall polygon, streets from gates to center via shortest paths on the Voronoi graph, wards subdivided by recursive oriented bisection ("lot cutting") into buildings. Use as a reference only: GPL would infect the project if code is copied. Watabou's page says maps may be used freely, but this concerns output, not code. Re-implement the ideas.
- Python reference/dependencies: [josauder/procedural_city_generation](https://josauder.github.io/procedural_city_generation) (verified; Python, numpy/scipy/matplotlib, Blender export, Parish-Mueller-style, old Python 2.7 era, check license), `shapely` (BSD) for polygon ops, `scipy.spatial.Voronoi`, `networkx` (BSD) for graph/shortest paths, `skimage.graph.route_through_array` (BSD) for slope-cost paths, `streamlines` can be hand written with RK4 (about 150 lines).

### Recommended hybrid for "natural, flowing, not boxy"
1. Inputs: lasso polygon (feet), heightmap, optional river/road lines, scale.
2. Rings: compute a center point (user-picked or polygon pole of inaccessibility, `shapely.ops.polylabel`). District by normalized distance: core (authority, plaza) -> commoner ring -> outskirts/farms. Farms feather out: lots become big irregular fields with decreasing density and a noise-thresholded boundary (no hard edge); building density = smooth falloff function times noise.
3. Plazas: pick plaza count from area (e.g. one per ~N acres; area above threshold gets a main plaza at center plus smaller squares at major junctions where 3+ arterials meet). Plaza is an irregular polygon (buffer circle with noise), carved from the street network and flagged as open space.
4. Streets: tensor field = blend of (a) radial field around the center (or around the plaza), (b) a contour-following field: direction = perpendicular to the terrain gradient, weighted by slope (steeper -> more weight, so streets run along contours), (c) a downhill field for a few "ramp" streets, (d) river-following field near water. Trace major (arterial) streamlines from the gates / entry points (pass, bridge) toward the center, minor streets filling by separation distance (seed spacing dsep, as in Jobard-Lefer streamlines). Slope handling: cap grade by limiting streamline direction so grade <= about 10-12%; where the required climb exceeds that, rotate the heading toward the contour direction and zigzag (switchbacks emerge automatically). Cost-based alternative for key roads: A* over the heightmap with cost = distance * (1 + k*grade^2) and a river-crossing cost except at the bridge.
5. Terraces: for towns spanning several levels, flatten building platforms (smooth the heightmap inside each block toward the block's mean height with a feathered blend) and optionally add retaining-wall lines at steps; export the modified heightmap so contours reflect it.
6. Blocks: build planar graph from streamlines (`shapely.ops.polygonize` after `unary_union` of the street lines), shrink by half street width (negative buffer) to get blocks.
7. Lots / buildings: recursive oriented-bounding-box bisection (Watabou/Parish style): split the block along the shorter axis midpoint with random jitter in ratio and angle; stop at target lot area per district (small deep lots in core, bigger in ring, none in farm zone); drop lots without street frontage; inset for setbacks and gaps; building footprint = lot inset with random chamfers. Keep rotation aligned with the nearest street rather than world axes to avoid the grid look. Rejects: slope above limit.
8. Output: world-model JSON entities (`streets.json` polylines with width_ft, `blocks`, `buildings`), status `proposed`, stable ids. Bridgehollow's authority buildings are placed by name into central lots (the generator must allow pinning named buildings to center lots).

Recommendation (item 3): Python, tensor-field streets seeded from the terrain (own implementation, with Chen et al. as the reference) + Watabou-style ring/ward and lot bisection (own implementation of the ideas, no GPL code), shapely/scipy/networkx/numba as dependencies. Do not vendor TownGeneratorOS (GPL). ProbableTrain's MapGenerator is the best code reference for tensor-field logic if its MIT license holds.

## 4. Phase-based terrain shading (3D Canvas style)

I could not find public documentation for the phase system; the following is a design built from the requirement ("ordered texture phases, each with elevation range vs slope-angle rule, blend ranges, reorderable"). It matches how splat-map/terrain shaders work (e.g. Unity/Godot layered terrain).

Data model (per phase): `{id, name, texture/fill, elev_min, elev_max, elev_blend, slope_min, slope_max, slope_blend, noise, opacity, enabled}`. Phases are ordered list; later phases paint over earlier ones (reorder = change order, which changes who wins where ranges overlap).

Algorithm (Python, numpy):
1. slope = degrees(arctan(hypot(dz/dx, dz/dy))) using feet-consistent pixel size; optionally Gaussian-smooth to avoid speckle.
2. For each phase compute weight w = smoothstep window on elevation (rises over elev_blend below elev_min, falls above elev_max) times smoothstep window on slope, times optional noise perturbation of the thresholds (value-noise added to elevation and slope before the test, makes edges organic).
3. Composite in order: `out = lerp(out, phase_color_or_texture, w*opacity)`. Textures: tile the phase fill (PNG/pattern) in world coordinates, optionally triplanar not needed in 2D.
4. Hillshade multiplied on top: `shade = cos(zenith)*cos(slope)+sin(zenith)*sin(slope)*cos(azimuth-aspect)`, azimuth 315, as an optional separate layer; slider for strength and light angle.
5. Output as raster PNG (placed linked image in `ART - Textures`/`LINES/Terrain-shade` layer) at e.g. 150-300 ppi of the page. For SVG-friendly vector output, threshold each phase's weight at 0.5 and vectorize (`contourpy` filled contours or `skimage.measure.find_contours` on the weight) into compound paths with feathered gradient not possible; so offer both: raster for soft blends, vector for hard-edged stylized maps.
6. Defaults/presets: grass (low elev, slope < 20), rock (slope > 35 at any elevation), scree (slope 25-35, mid elev), snow (elev > threshold, slope < 45), dirt/path override from road mask, riverbank sand near water. Sliders map directly to elev/slope ranges and blends; reordering is drag/up-down buttons.

Recommendation (item 4): implement as raster composited in Python with smoothstep windows and noise-jittered thresholds, plus optional hillshade; export a PNG per phase mask (so the artist can re-use masks in Illustrator as opacity masks) and the composite; vector option via thresholded masks.

## 5. Architecture

Division of labor:
- Python (`illustrator/` generator, runs on the PC; can use the GPU for erosion via CuPy/PyTorch if desired):
  - terrain.py: control lines + params -> heightmap (.npy + 16-bit PNG), seed.
  - contours.py: heightmap -> contour polylines, index flags, label placements, masks applied.
  - shade.py: heightmap + phase list -> shaded PNG (+ masks).
  - town.py: lasso polygon + heightmap + params -> rings, plazas, streets, blocks, buildings -> world JSON.
  - All write into the world model (JSON) and a draw-command/job-result JSON consumed by the existing panel actions (`replace_layer`, `lock_layers`). Every output is deterministic from (params, seed).
- CEP panel (HTML/JS UI + ExtendScript via `evalScript`), must only: show controls, write job JSON, trigger/poll for results, and draw. Needed UI:
  - Terrain: seed, overall relief, ridge sharpness, erosion strength, sea/valley level, per-side mountain strength (N/E/W), entry-pass position/width, "draw control lines" buttons (ridge, valley, pass, platform, spot height) that read selected paths from named layers.
  - Contours: interval, index every N, units (ft/m), vertical exaggeration, font, size, label spacing, min curvature, mask toggle + which layers mask (buildings, streets), stroke styles per index/normal, minimum length.
  - Shading: phase list (add/remove/reorder, drag handles), per-phase elevation min/max/blend and slope min/max/blend sliders, texture picker/preset, opacity, noise, hillshade toggle/azimuth/strength. Live preview: render low-res PNG on each change (debounced) via Python job and show in the panel as an `<img>`; the final render is separate.
  - Town: "Use selection as area" button, center picker, density, ring sizes (authority / commoner / farm feather), plaza threshold, max street grade, street width, organic-vs-grid slider, blocks on/off, building outlines on/off, textured fill choices per part, preset dropdown, seed + "reroll", "mask contours".
- Job/result protocol: panel writes `jobs/<id>.json` (all params + geometry), the Python watcher (or the existing bridge) writes `results/<id>.json` plus PNGs; the panel reads them with `cep.fs`/`window.cep.fs.readFile` or ExtendScript `File`, and draws via ExtendScript.

Illustrator selection / lasso limits (relevant verified findings):
- ExtendScript can read the user's selected path: `app.selection[0].pathPoints` gives `anchor`, `leftDirection`, `rightDirection` per point (see [PathPoint reference](https://illustrator-scripting-guide.readthedocs.io/jsobjref/PathPoint.html), verified). For compound paths and groups, `app.selection[0].pathPoints` is not directly available; iterate `pathItems` inside `compoundPath` / group `.pathItems`.
- The **Lasso tool selection area itself is not readable**: scripts can set a selection region from points but cannot read it back ([community thread](https://community.adobe.com/t5/photoshop/get-a-list-of-points-used-in-a-lasso-selection-from-a-cep-event/m-p/10950299) is about Photoshop; I recommend assuming the same for Illustrator). Lasso only selects existing objects/anchors. So: do not rely on the Lasso tool as a geometry input. Instead instruct the user to draw a closed path with the Pen/Pencil/Blob tool (or lasso-select an existing shape) on a dedicated layer `TOWN AREA` (any path there is an area), and the panel's "Use selection as area" reads that closed path. Bezier handles are flattened to a polyline in Python (sample each segment at ~1 ft or 8-16 points per curve).
- Coordinate conversion: Illustrator uses points with origin per artboard and y up; convert with the artboard rect and scale preset (1 in = 100 ft = 72 pt, i.e. 1 pt = 1.389 ft) to the world model feet y-down.
- ExtendScript is ES3: no native `JSON` (include json2.js; the panel's CEP side has real JSON in JS, so stringify on the CEP side and have ExtendScript return simple strings), no `Array.map` etc. File I/O via `File` objects; encoding UTF-8 must be set explicitly.
- Many anchors in large outputs: build paths with `pathItems.add()` and `setEntirePath(points)` (fast), not point-by-point; place the work inside a single layer lock/hide to avoid redraw cost.
- Selection-based inputs for other lines (ridges, rivers) work the same way: read selected paths, names preserved.

Recommendation (item 5): thin panel, fat Python. Job JSON with params plus polylines (selection or named layer), Python returns draw-commands JSON and PNGs; panel draws into GEN layers with `replace_layer`. Area input = closed path in a `TOWN AREA` layer or current selection, not the Lasso tool.

## Top recommendation summary
1. Terrain: constraint-interpolation + domain-warped ridged fBm + thermal/stream-power erosion (numpy/numba), user-drawn ridges/valleys; terrain-diffusion optional for a far backdrop only.
2. Contours: `contourpy` on smoothed heightmap, shapely simplify/Chaikin, shapely difference for masks, rotated-box collision-aware labels on index contours, emit anchors + text rotations.
3. Towns: own implementation of tensor-field streets seeded by terrain and rings (Chen et al. as reference, ProbableTrain/MapGenerator as code reference) plus oriented bisection lots; avoid copying GPL TownGeneratorOS.
4. Shading: ordered phase list with smoothstep elevation and slope windows, noise-jittered thresholds, composited in order in numpy, optional hillshade; raster for soft blends, vector via thresholded masks.
5. Architecture: panel = UI + job JSON + drawing; Python = everything computational; area input via drawn closed path (Lasso area is not readable), json2.js for ExtendScript.

## Sources
- https://github.com/xandergos/terrain-diffusion
- https://danial-barazandeh.github.io/Earthbender
- https://arxiv.org/pdf/2505.04050
- https://pubs.cs.uct.ac.za/id/eprint/1583/1/Diffusion%20Terrain.pdf
- https://aryamaanjain.github.io/pdf/2026/pixels2peaks.pdf
- https://www.sci.utah.edu/~chengu/street_sig08/street_project.htm
- https://docs.rs/crate/symbios-tensor/0.1.0
- https://github.com/watabou/TownGeneratorOS
- https://github.com/panicmod-e/ProceduralCityGenerator
- https://josauder.github.io/procedural_city_generation
- https://github.com/scikit-image/scikit-image/blob/v0.14.1/skimage/measure/_find_contours.py
- https://illustrator-scripting-guide.readthedocs.io/jsobjref/PathPoint.html
- https://community.adobe.com/t5/photoshop/get-a-list-of-points-used-in-a-lasso-selection-from-a-cep-event/m-p/10950299
- https://foundryvtt.com/packages/canvas3dcompendium (3D Canvas companion pack; no phase documentation found)
