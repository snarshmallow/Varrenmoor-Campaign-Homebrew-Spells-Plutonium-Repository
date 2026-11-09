# G10 - Panel GUI redesign: clearer settings, less "data entry then Apply" (queued 2026-11-09, user: "later")

User request (verbatim): "then later spin up opus to redo gui to make all settings and parameters more clear and less like data entry > apply"

Start only after the current batch finishes (Eirwitch camp scene, building editor, fast item delete, orientation audit, street scene batch + refresh). Use an Opus agent.

Goals:
- Every setting explained in plain language right where it is (what it does, units, typical range, what changes visibly), with sensible defaults and presets instead of bare number boxes.
- Live feedback instead of "type numbers, press Apply": sliders, steppers, toggles, swatches, thumbnails/previews that update as values change (debounced), before/after, undo.
- Group parameters by intent (e.g. "Terrain shape", "Water", "Look") with progressive disclosure (basic first, advanced folded), consistent tab layout, search across settings.
- Profiles (already built) used as the main way to switch whole looks; show diff of what a preset changes.
- User addition (2026-11-09): the redesign MUST include clearly styled RED delete buttons (consistent destructive styling, two-click or confirm-tick arm, never window.confirm) and EDITABLE text/fields everywhere: every name, id, label, note and value shown in a list or table can be edited in place (inline edit with Enter/Esc, validation and undo), everywhere a thing can be deleted there is a red delete, and nothing important is read-only text.
- Keep all CLI parity (lib/command_manifest.json + test_command_parity.js), ES5 panel code, publish-on-window rule, loader list, no window.confirm/alert/prompt, reload button, and all existing job wiring.
- Verify with the Edge/CDP browser harness (panel/test/browser) and node tests; screenshots of before/after for the user.
