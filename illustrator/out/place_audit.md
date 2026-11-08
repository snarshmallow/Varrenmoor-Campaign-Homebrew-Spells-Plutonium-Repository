# Bridgehollow-specificity audit

Question: if we draw another town, can anything make it look or behave like Bridgehollow? Method: grep of every generator, preset, panel file and
world script for Bridgehollow names, coordinates (1200/750, 2400x1500), elevations (660, 700, 910, 1000 ft), district / street / building names, and
hand reading of town_gen, town_area, terrain_natural, shading, skybox, viewcfg, winter_build, core.js, main.js. Regression: regenerating Bridgehollow
(default seed) with the changed code is byte-identical (streets, districts, report, 148 buildings, heightmap); `test_place_create.py` checks it.

Severity: H = a new place would visibly inherit Bridgehollow; M = wrong result in some terrains / kinds of place; L = default, comment or label only.

| # | file:line (after fixes where noted) | Bridgehollow-specific thing | Sev | Fix |
|---|---|---|---|---|
| 1 | town_gen.py DEFAULTS (ring names "Authority Ward", "Commoners' Ring", ids authority/commoner) | default districts were Bridgehollow's | H | defaults now neutral ("Civic Quarter", "Town", ids core/town); Bridgehollow params carry their own rings so output is unchanged |
| 2 | town_gen.py DEFAULTS `entry` name "Pilgrim Road", id pilgrim_road; to_model "Pilgrim Bridge" | road and bridge names | H | name comes from the naming set (`entry_roads`); bridge name derived from the road name ("X Road" -> "X Bridge") or `entry.bridge_name` |
| 3 | town_gen.py `street_name` (3 fixed name banks) | every town got Cartwright Lane, Dyers Walk, Warden Street ... | H | banks read from presets/naming/<set>.json (`naming_set` param); sets: fantasy_generic, scandinavian, danish_german, english, bridgehollow_legacy |
| 4 | town_gen.py `place_named` (Warden's Hall, Magistrate's Court, Tax Office, Lockup, ids bld_warden_hall ...) | named civic buildings, notes ("Pilgrim Road", "low rise") | H | names, ids and notes from the naming set; `named.skip` drops any of them (hamlets have no court or lockup); the Bridgehollow set reproduces the old text exactly |
| 5 | town_gen.py smithy scoring `abs(dist_c - 300)` | ring radius 300 ft = Bridgehollow's commoner ring | M | `named.smithy.ring_ft`, set from the place's ring radii by place_create; default 300 kept |
| 6 | town_gen.py `district_ents` notes ("Wardens, court, tax office ...", "Commoners' homes") | district text | H | `district_notes` in the naming set |
| 7 | town_gen.py ring_spec.centre default [1200, 750] | centre of a 2400x1500 map | H | default None -> middle of the place; place_create picks the flattest dry ground |
| 8 | town_gen.py district_ents: no closed contour at r_max returned an empty ring | single-ring towns lost their district | M | ring reaches past the area -> the whole area |
| 9 | town_gen.py mill | placed even with no river | L | skipped silently when the place has no river |
| 10 | terrain_natural.py `_defaults` hills_south y_start 1150, amp 26 | every "natural" spec got Bridgehollow's southern foothills | H | `natural.defaults_version: 2` (written by place_create) turns them off; specs without the key keep the legacy numbers so the committed terrain is identical |
| 11 | terrain_natural.py enforce_river `exp(-h/k)` | underflow -> NaN above about 2200 ft (assumed Bridgehollow's 600-1100 ft) | M | shifted log-sum-exp; heightmap of Bridgehollow verified bit-identical |
| 12 | terrain_check.py (basin box 750-1650 x 450-1250, rise at 1200,700) | fixed pixel window | L | same window expressed as fractions of the map size |
| 13 | presets/terrain_phases/*.json (elev_min/max 700, 740, 820, 960 ...) | absolute elevations tuned to a 625-1002 ft bowl: a coast at 20 ft is all one band, a pass at 2000 ft all snow | H | `place.json phase_elevation: "percentile"` maps the thresholds onto the place's own p02..p98 relief (place_stats.py, applied in shading.render via worldio meta); shore bands stay datum-relative; Bridgehollow has no key -> unchanged |
| 14 | skybox.py treeline 910, low ground 760, snow_ft 1000/1040 | same absolute heights | H | same remap (place_stats) |
| 15 | skybox.py far ranges "never lower than 4 degrees so the bowl stays closed" | closed-bowl horizon on every place | M | `place.json skybox {rim_min_deg, far_scale}`; place_create sets an open horizon for coast / island / plain |
| 16 | viewcfg.py FALLBACK town focus [1200, 750] | | L | "center" |
| 17 | winter_build.py (hard-coded world/bridgehollow, glow positions, windows 400,250,2000,1250 / 880,550,1520,950, no --place passed to subtools) | whole script was Bridgehollow's | H | `--place`; windows from the place size and view_focus (Bridgehollow gets the same numbers); glow from the place's inn / craft / civic buildings |
| 18 | skybox.py / README text "Bridgehollow skyboxes" | wording | L | reworded |
| 19 | panel/lib/core.js river-meander job called world/gen_bridgehollow.py for every place | M | other places go through `place_create.py regen` (same flags) |
| 20 | panel index.html: "River meander (Bridgehollow)", placeholders "Authority Ward", "Bridgehollow overview", ring-guide text | L | neutral wording |
| 21 | panel main.js placeCentre fallback 2400/1500 | L | 0 when place.json has no bounds |
| 22 | panel core.js defaults: terrain seed 1103, base 660, entry 1290/1480, town seed 1103 | UI values shown before the place's own files load | L | NOT changed: overwritten when a place is loaded (`*_loaded` flags); listed so nobody mistakes them for place data |
| 23 | presets/label_abbreviations.json (Authority, Commoners', Warden's ...) | only matters if those words occur | L | other cultures' words added (Strasse, Harbour, Courthouse ...) |
| 24 | presets/label_presets.json preset "bowl", view name "bowl" | name of the whole-place overview, works on any place | L | name kept (renaming would break saved states); documented as "overview" |
| 25 | presets/padding/bowl-ridge.json etc. | named for terrain types, not for the place; defaults chosen per terrain recipe | L | place.json defaults.padding_preset |
| 26 | `--place` default "bridgehollow" in 20 CLIs (render_world, shading, worldpack, foundry_push ...) | convenience default only | L | kept; every tool takes --place |
| 27 | gen_bridgehollow.py, water.py selftest numbers, building_styles_preview.py default pack, tests | Bridgehollow-only scripts / test fixtures | L | by design; the generic path is place_create.py |
| 28 | building_styles `auto` | weights by kind and district id, not by names | OK | no change; place_create writes culture style sets per kind |
| 29 | worldpack.py z_origin = floor(min/10)*10, foliage zones, lighting defaults | derived from the place | OK | no change |
| 30 | panel_state.json shading phases copied from the Bridgehollow preset | per-place saved state | L | with phase_elevation set the saved thresholds are remapped too (shading.render does it) |

Not fixed, on purpose: town_area.py comment about "15 acres of flat floor" (comment only; the numbers are slope based);
terrain `keep_clear` / `peaks` such as "authority rise" live in Bridgehollow's own terrain_spec.json.

Known limits of the generic path: the street generator is one tensor-field method (layouts organic, radial, grid, linear, walled are parameter sets
for it, so a "grid" is a strong grid bias, not a perfect lattice); plazas can fail to fit on a very narrow pass floor; the town wall is written to
walls.json and drawn in the 2D map but not exported to the 3D pack.
