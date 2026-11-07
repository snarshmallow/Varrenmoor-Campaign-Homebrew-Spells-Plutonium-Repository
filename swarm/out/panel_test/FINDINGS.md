# Varrenmoor Bridge panel check (Desktop operator)

Date: 2026-11-07, around 9:25 AM local. Host: Illustrator 2024 on this PC (Chrome not involved).
Access: Adobe Illustrator 2024 granted by the user in chat (full tier) after a first request was denied.

## What was done
- The Varrenmoor Bridge panel was already open and docked. I did not use Window > Extensions. Its header reads "Varrenmoor Bridge" and its status reads "idle".
- Tab row read: Scale, Terrain, Contours, Shading, Water, Town, Layers, Foundry. All labels are legible in the zoomed captures.
- Clicked the Terrain and Layers tabs (several attempts each). I did not click Apply (regenerate guides), Redraw all GEN layers, New document + draw, or Reload. No world files were touched and nothing was saved.
- Did not open or close any document.

## Findings
1. **Tab clicks do not switch the panel content (blocking).** After 4+ mouse clicks on Terrain and Layers, the body stayed on the Scale page. The Layers tab button shows a highlight, but its content does not appear. I could not check Terrain, Contours, Shading, Water, Town, Layers or Foundry content. This needs a look at the panel (focus or click target), not a retry from this side.
2. **Header reflows while a job runs.** When job pt10 ran, an orange "job file pt10" label appeared and wrapped the Log and Cancel controls onto a second row. The tab row shifted down about 20 px, so fixed click positions go stale. Cosmetic, but it moves the tabs.
3. **Scale tab:** Preset "town", scale 100 ft per inch, grid 100 ft, major every 5, page 17 x 11 in, units ft, Python executable "python", shading dpi 150. Readable; no clipping seen.
4. **Ping job ping_r1:** completed (illustrator/jobs/done/ping_r1.result.json: ok true, version 28.2.0, docs 4).
5. **Other panel jobs ran during the check:** pt1 to pt10 (9:23 to 9:26 AM). I did not queue these; they came from the coordinator's side. pt9 and pt10 save to illustrator/out/paneltest_final.ai and paneltest_ids.ai.
6. **Open documents:** the tab bar now shows several unsaved documents (asterisks) plus paneltest_ids.ai, paneltest_final.ai and others. The bridgehollow_town_v3 [Recovered].ai tab is no longer in the bar. I did not close or save any of them.

## Screenshots (this folder)
- 01_scale_tab_zoom_start.jpg: Scale tab at the start.
- 02_full_screen_town_view_after_job_pt10.jpg: full screen with the town map from the job.
- 03_terrain_click_no_change.jpg: Terrain click, no tab change.
- 04_full_screen_terrain_retry_no_change.jpg: full screen after retry, still Scale content.
- 05_header_job_file_pt10_wrapped.jpg: header wrapped by "job file pt10".
- 06_layers_click_no_change.jpg: Layers click, no tab change.
