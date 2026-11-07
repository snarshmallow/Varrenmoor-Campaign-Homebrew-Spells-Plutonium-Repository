# Bridgehollow town v4 (graded streets, fuller bowl)

Files: `bridgehollow_town_v4.svg/.png` (bowl view, contours on). v3 files are untouched. Seed 1103, detail 2, same terrain and water.
Regenerate: `python world/gen_bridgehollow.py` then `python illustrator/generators/render_world.py --view bowl --contours --out illustrator/out/bridgehollow_town_v4.svg`.

## Metrics, v3 -> v4
| | v3 | v4 |
|---|---|---|
| Buildings | 91 (75 houses) | 139 (122 houses, 3 sheds, 2 farmhouses, 2 barns, 6 civic, inn, stables, 2 craft) |
| Street grade, raw heightmap, 40 ft window: max | 0.114 (Pilgrim Road at y 1050, near the river bank) | 0.081 (Pilgrim Road) |
| Streets over the 0.08 cap on raw terrain (40 ft) | 11 of 30 | 1 of 36 (by 0.001) |
| Same, 20 ft window | max 0.121 | max 0.094, 7 streets over 0.08 |
| Street grade on the graded bed (what `elevations_ft` holds) | 0.128 (str_006) | 0.060 max, none over cap; cut/fill limited to 3 ft |
| Pilgrim Road | 683 ft straight run up the east bank, 0.114 | switchbacks above the pass, 0.081 raw / 0.06 bed |
| Pilgrim Bridge deck grade | 2.2 ft over 95 ft (0.023) | 0.9 ft over 95 ft (0.009) |
| Authority rise slope (district polygon, raw 15 ft smoothed) | mean 0.083, p90 0.108, max 0.283 (river trench inside it) | mean 0.074, p90 0.089, max 0.104 |
| Buildings x extent | 776-1492 | 777-1576 (east side now built up to the east foothills) |
| Plazas | 3 (one stranded at the west edge) | 2 (Market, Court) |
| Fields | 6 (133k ft2) | 7 (103k ft2), now feathered along the south and east edges of the floor |

## What changed
- Ring plan: centre (1100,780) beside the river, ellipse aspect 0.8 x 0.95, authority r 210, commoners r 490, farms beyond. Commoner dsep 62-76 ft, lots 420-900 ft2, backland lots within 32 ft of a street can be built, house footprint capped at 46 x 38 ft. All in `town_params.json`; the panel Town tab fields (rings radius/width/lot sizes, grades) read the same keys. `panel_state.json` town block updated to match (it is untracked).
- Grades: A* (Pilgrim Road) now sees the real river bank (`limits.bank_fill_ft` 18, was 45), weights grade cubically (`entry.grade_weight` 6, `grade_exp` 3) with `max_main_grade` 0.04, so it zig-zags instead of climbing the bank. Streamlines are traced at 0.6 x the cap (`streets.trace_grade_margin`). Any interior stretch whose raw grade exceeds the cap is cut out (`streets.split_steep_factor` 1.0) and the remainder re-pruned. Every street gets a graded bed (45 ft smoothing, `limits.max_cut_fill_ft` 3) and `grade_max` (bed), `grade_raw_max`, `cut_fill_ft` per street; the report has `street_grade_raw_max`, counts and lengths over cap.
- Layout: zig-zag removed from streamlines (`streets.smooth_sigma_ft` 12; hairpin kinks 20 -> 5 streets); stubs under 110 ft with a free end and thin or tiny loops (the teardrop) removed (`stub_min_ft`, `loop_max_area_ft2`, `loop_compact`); river drawn as a solid bank line in `render_world.py` (the dashed proposed style made it read as a wide dashed band); ring labels sit on their side of the ward.
- New code knobs default to off or to the old behaviour, so other places are unchanged; `test_town_gen.py` passes.

## Remaining honest caveats
- Raw terrain is not strictly under 0.08 everywhere: Pilgrim Road peaks at 0.081 (40 ft window) and at 20 ft windows seven streets reach 0.08-0.094 (worst Brook Lane 2 at about (1526,860), a hillside edge street). They are within the 3 ft cut/fill allowance (bed max 0.06) but would need cuts if built.
- Building count is 139; farmsteads fell from 4 to 2 (more of the floor is town now). Streets still end bluntly at the area edge in a few places.
- The east side is town up to about x 1500 then foothills; farmland is a thin band there because the floor is only about 300 ft wide east of the river.
