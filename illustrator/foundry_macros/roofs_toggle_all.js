// Varrenmoor: Roofs - toggle ALL roofs of this scene (GM). Works for roof modes per_building and per_scene.
// Roof tiles carry flags.varrenmoor.roof (written by foundry_push.py push-models). Hiding = the tile's own `hidden` flag, so it is saved with the scene and
// every player sees it at once. The GM still sees hidden roofs as a 50% ghost (3D Canvas behaviour), players see nothing.
// Install: python illustrator/generators/foundry_push.py install-roof-macros   (or paste this text into a new Script macro).
if (!game.user.isGM) return ui.notifications.warn("Only the GM can toggle roofs.");
const scene = canvas.scene;
const roofs = scene?.tiles.filter((t) => t.getFlag("varrenmoor", "roof")) ?? [];
if (!roofs.length) return ui.notifications.warn("This scene has no roof tiles (push models with --roof-mode per_building or per_scene).");
const hide = roofs.some((t) => !t.hidden);                // any roof still visible -> hide all, otherwise show all
await scene.updateEmbeddedDocuments("Tile", roofs.map((t) => ({ _id: t.id, hidden: hide })));
ui.notifications.info(`${hide ? "Hid" : "Showed"} ${roofs.length} roof tile${roofs.length === 1 ? "" : "s"}.`);
