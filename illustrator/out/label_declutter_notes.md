# Label declutter: before / after (Bridgehollow v7 fills + phased shading)

Before = `--label-preset legacy` (old first-fit placement, black 0.4 pt leaders, nothing hidden). After = new defaults with the `bowl` preset (bowl) and the `working` preset (town 100 and 40). Same terrain, fills and contours; Label QA numbers from `illustrator/generators/label_declutter.py` (written next to each SVG as `out/label_declutter/<view>_<before|after>.svg.labels.json`).

| View | | shown | hidden (scale / no room) | with leader | text over map features | labels over 25 % | label overlaps | leaders crossing labels |
|---|---|---|---|---|---|---|---|---|
| Bowl 200 ft/in | before | 23 | 0 (0 / 0) | 14 | 45.9 % | 16 | 0 | 1 |
| Bowl 200 ft/in | after | 21 | 136 (136 / 0) | 19 | 4.1 % | 3 | 0 | 0 |
| Town 100 ft/in | before | 33 | 0 (0 / 0) | 13 | 51.0 % | 23 | 1 | 0 |
| Town 100 ft/in | after | 33 | 133 (133 / 0) | 14 | 22.9 % | 14 | 0 | 1 |
| Town 40 ft/in | before | 31 | 0 (0 / 0) | 6 | 40.4 % | 17 | 1 | 0 |
| Town 40 ft/in | after | 31 | 78 (0 / 78) | 6 | 15.5 % | 8 | 0 | 0 |

Features counted: buildings, plazas, road surfaces, water (the river). A label inside its own building does not count against it. The river is wide at 40 ft/in, so most of the remaining overlap is names sitting on or beside the water (Town Treasury, Meeting Hall).

## Pictures

Full pages (Illustrator export, embedded rasters, .ai saved with them): `label_declutter_bowl.png/.ai`, `label_declutter_town100.png/.ai`, `label_declutter_town40.png/.ai`; before: `label_declutter_*_before.png`.

## What changed in the centre

- Bowl and town: the stacked block Court Square / AUTHORITY WARD / Warden's Hall / Records House / COMMONERS' RING / Customs House on the town centre is gone: area names slide to the emptiest ground inside their district (or move out with a leader), civic names use empty ground, leaders are white with a dark casing and read on streets and fills.
- At 200 ft/in only districts, plazas and civic buildings are labelled (136 street and house labels sit in `LABELS / Labels - Hidden`, a hidden layer); at 100 ft/in streets appear; at 40 ft/in houses that fit inside their roof are labelled (no leaders for houses by default).
- Pilgrim Bridge, street names: placed at the best of five positions along the street (least map covered) instead of always the middle.

## Not verified live

The new Illustrator host actions (`reroute_leaders`, `read_label_positions`, `move_item`, `read_items`, `lock_leaders`) and the panel live mode load only when the panel is reopened; they are covered by a mock-Illustrator test (`node illustrator/panel/test/test_host_reroute.js`). See the report for the live check that was run.

## Update: water and grouping

Offset labels never sit on water now (water weight 4.0, hard rejection unless no alternative; leaders crossing water/roads are penalised): text over water is 0 % in all three views (it was 12-17 %). Roads weigh 1.0. Each label is grouped halo + text as `<id>_callout` (host `finalize_labels`). Check image: `label_declutter_town40_v2.png/.ai`.
