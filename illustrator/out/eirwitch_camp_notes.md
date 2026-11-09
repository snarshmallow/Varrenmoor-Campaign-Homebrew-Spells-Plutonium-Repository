# Eirwitch Camp (Night)

Purpose-built place `world/eirwitch_camp` (NOT the older `world/mountain_pass_fort_town` "Supposed Eirwitch Camp", which is untouched).
Driver: `illustrator/generators/eirwitch_camp.py` (design / build / push / verify, all idempotent, `--dry-run` everywhere). Tests: `illustrator/generators/test_eirwitch_camp.py`.
Foundry scene: **Eirwitch Camp (Night)** = `Scene.r755aOD0XwiusHcw` (10 px/ft, 5 ft grid = 50 px, 12000 x 9000 px).

## Layout (feet; origin north-west, x east, y south; north is up)

```
 y=0   NW peak (~3660)        N ridge            | gorge |      NE crags
       ...........dense pines.....................|  ~~~  |.......pines........
 y=422            [stave church 14x20, door S]    |  ~~~  |
 y=470  pines   ( clearing r=65, FIRE at 560,470 )==footpath==[rope bridge 108 ft]==ledge==footpath -> E edge (1200,590)
 y=494       Witch Road ends 520,494 (dead end)   |  ~~~  |
 y=655 W edge --- Witch Road (12 ft dirt) --------|  ~~~  \
 y=900  pines (lower, south-west)                          \~~ fjord arm (SE, level 3072) ~~
```

| Feature | Where / size |
|---|---|
| Clearing | centre (560, 470), level radius 65 ft at 3198-3200 ft (+-3 ft natural unevenness), blended out over 70 ft |
| Campfire | exactly at (560, 470): 11-stone ring, 6-log teepee, ember bed, 3 emissive flame cones (no particles), 2 log benches at 8 ft; 403 tris (layer `props`, collision on) |
| Stave church | `bld_eirwitch_church`, footprint 14 x 20 ft (long axis N-S), centre (560, 422), 2 floors, door on the south gable facing the fire (38 ft away); preset `eirwitch_stave_church` (new; `stave_church` untouched): near-black tarred boards, pitch 1.45-1.5, 3 stepped tower tiers + needle spire, dragon-head finials, snow on the roofs; about 58 ft from the plinth to the finial tip (walls 23 ft) |
| Witch Road | `str_witch_road`, 12 ft dirt lane, no kerb, from the west edge (0, 655) at 3131 ft up to the clearing (max grade ~11 %), dead-ends at (520, 494) inside the clearing; does not reach the gorge |
| Gorge | axis (775,-20) -> (790,470) -> (1110,880); flat floor 36 ft, walls 34 ft run (cliff at the rim, talus at the foot), rim-to-rim ~100 ft, ~106 ft deep at the bridge; floor 3112 -> 3074 ft north to south |
| River | `wat_gorge_river`, 24 ft wide, on the gorge floor, flows south into the fjord |
| Fjord arm | `wat_fjord`, ellipse in the south-east corner, water level 3072 ft, floor 3040, steep walls |
| Rope bridge | `brg_str_gorge_path_1`, preset `rope_plank`, 3.5 ft deck, span 108 ft (738 -> 846 at y 470), deck ~112 ft over the river |
| Footpath | `str_gorge_path`, 4 ft: clearing edge (626,470) -> west rim -> bridge -> rocky ledge (868,470) -> east edge (1200, 590) |
| Mountains | NW peak, N ridge, NE crags (up to ~3660 ft), terrain falls to the south-west and to the fjord |
| Forest | 2,7xx conifers (spruce 4 : scots pine 3 : fir 2) at 360 / ha + juniper / boulders; none in the clearing, on the road / path corridors, in water or on walls steeper than 40 deg; winter atlas; impostors beyond 320 ft of the scatter centre |

Terrain: the blank place's highland_ridge heightmap (seed 1713) supplies only roughness; the designed relief is saved as ONE heightmap edit layer
(`world/eirwitch_camp/heightmap_edits.*`, panel: Terrain > Paint heightmap; "Reset to generated terrain" removes the design).

## Lighting (night)
Sun preset `night` (moon az 120 / alt 35, same direction in the generated sky `sun_night_night_az120_el35`), ambient 0.14, shadow bias -3e-4, no fog.
Lights (4, budget 6): campfire 1800 K (#ff7e00-ish), dim 50 / bright 15 ft, torch flicker, the ONLY shadow-casting light; three faint warm church window glows
(dim 12 / bright 3, no flicker, no shadows). Pipeline-derived interior lights are dropped.

## Rebuild
```
python illustrator/generators/eirwitch_camp.py design     # place, terrain, water, roads, church, door, foliage (~10 s)
python illustrator/generators/eirwitch_camp.py build      # export -> rope bridge -> split -> merge -> campfire + lights -> night sky (~50 s, >= 3 GB free RAM)
python illustrator/generators/eirwitch_camp.py push       # updates Scene.r755aOD0XwiusHcw in place (found by its pipeline flag)
python illustrator/generators/eirwitch_camp.py verify
python illustrator/generators/test_eirwitch_camp.py
```

## Approximate / not verified
* Fjord/gorge realism: analytic profile on a 6 ft grid (no overhangs, walls ~70 deg), fjord arm is a still lake polygon, not tidal sea.
* Church: tier geometry from the generic `tiers()` builder (square tower stepping in), no svalgang gallery; total ~58 ft incl. the finial.
* Clearing is level to about +-3 ft (natural), not a perfect plane.
* Not checked in the GM tab by me: frame rate, look of the rope bridge / flames / sky; scene totals 52 model tiles, ~519k triangles (foliage 443k).
* The world pack export (`world/eirwitch_camp/export`, 53 MB) is not committed; `build` regenerates it.
