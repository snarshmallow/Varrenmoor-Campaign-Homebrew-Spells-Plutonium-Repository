// Varrenmoor: Roofs - toggle the roof of ONE building (GM), per_building mode. Works for per_scene too (then it toggles the single roof tile).
// Which roof: (1) selected roof tile(s); else (2) the roof over the selected token(s); else (3) a dialog listing every roof with checkboxes.
// Hiding = the tile's own `hidden` flag (saved with the scene, all players see it). The GM sees a hidden roof as a 50% ghost.
// Install: python illustrator/generators/foundry_push.py install-roof-macros   (or paste this text into a new Script macro).
if (!game.user.isGM) return ui.notifications.warn("Only the GM can toggle roofs.");
const scene = canvas.scene;
const roofs = scene?.tiles.filter((t) => t.flags?.varrenmoor?.roof) ?? [];
if (!roofs.length) return ui.notifications.warn("This scene has no roof tiles (push models with --roof-mode per_building or per_scene).");
const label = (t) => { const b = t.flags?.varrenmoor?.roof?.buildings ?? []; return b.length === 1 ? b[0] : `${b.length} roofs (${t.id})`; };
let targets = canvas.tiles.controlled.map((p) => p.document).filter((d) => roofs.includes(d));
if (!targets.length && canvas.tokens.controlled.length) {      // tile x,y is the model centre (pack convention)
  const over = (tok, t) => Math.abs(tok.x - t.x) <= Math.abs(t.width) / 2 && Math.abs(tok.y - t.y) <= Math.abs(t.height) / 2;
  const pts = canvas.tokens.controlled.map((p) => p.center);
  targets = roofs.filter((t) => pts.some((c) => over(c, t)));
  if (!targets.length) ui.notifications.warn("No roof above the selected token(s).");
}
const apply = async (list) => {
  if (!list.length) return;
  const hide = list.some((t) => !t.hidden);
  await scene.updateEmbeddedDocuments("Tile", list.map((t) => ({ _id: t.id, hidden: hide })));
  ui.notifications.info(`${hide ? "Hid" : "Showed"} ${list.length} roof tile${list.length === 1 ? "" : "s"}.`);
};
if (targets.length) return apply(targets);
const rows = roofs.slice().sort((a, b) => label(a).localeCompare(label(b)))
  .map((t) => `<label style="display:block"><input type="checkbox" name="r" value="${t.id}"> ${label(t)} ${t.hidden ? "(hidden)" : ""}</label>`).join("");
const res = await foundry.applications.api.DialogV2.wait({
  window: { title: "Toggle roofs" },
  content: `<div style="max-height:340px;overflow:auto">${rows}</div>`,
  buttons: [
    { action: "toggle", label: "Toggle checked", default: true, callback: (ev, btn, dlg) => [...dlg.element.querySelectorAll("input[name=r]:checked")].map((i) => i.value) },
    { action: "all", label: "Toggle all", callback: () => "all" },
  ],
  rejectClose: false,
});
if (res === "all") apply(roofs);
else if (Array.isArray(res)) apply(res.map((id) => scene.tiles.get(id)));
