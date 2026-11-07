# Varrenmoor Bridge panel re-check (Desktop operator)

Date: 2026-11-07, around 9:29 to 9:31 AM local. Requested by the coordinator job "re-check panel after fixes (commit 278cb95)".

## Done
- Commit 278cb95 ("Panel: fixes from live Illustrator test") is already in this branch's HEAD. I did not need to pull; it was not pushed by me.
- Dropped `illustrator/jobs/ping_r2.json` (`{"id":"ping_r2","actions":[{"action":"ping"}]}`). Result `illustrator/jobs/done/ping_r2.result.json`: ok true, version 28.2.0, docs 17.
- Clicked the panel's close control (top right of the panel frame). The panel stayed open.
- Clicked the Illustrator "Window" menu (three tries, one after Escape). No menu appeared in the captures.

## Not done
- **Panel not closed or reopened.** Without a working close or Window menu, I could not reopen it via Window > Extensions, so the coordinator's fixed build is not confirmed to be loaded.
- **Tabs not clicked in this run.** Earlier in the first check, clicks on Terrain and Layers did not change the panel content. I did not repeat tab clicks this time.
- **Header on one row during a job:** not verified. The ping job finished before my screenshot, and the header was on one row ("idle") at 9:29 AM.
- **Contours tab / Label offsets section:** not checked.
- Red error line: not seen; the panel did not reach the tabs.

## Why I stopped
Mouse input did not visibly reach Illustrator's panel controls or its menu bar. I did not restart Illustrator, because that would close the open unsaved documents, and I did not save anything. I did not click Apply, Redraw, New document, Generate or Accept.

## Screenshots (this folder)
- 01_before_close_9_29am.jpg: panel open before any action.
- 02_after_close_click_panel_still_open.jpg: after the close click; panel still open.
- 03_window_menu_click_no_menu.jpg: after the Window menu click; no menu.
- 04_escape_then_window_menu_no_menu.jpg: after Escape and another Window click; no menu.
