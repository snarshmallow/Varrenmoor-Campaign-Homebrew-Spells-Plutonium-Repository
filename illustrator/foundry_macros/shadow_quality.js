// Set my shadow quality: the 3D Canvas sun only casts shadows when each user's client setting "Shadow Quality" is above 0. The setting is stored per browser,
// so no scene flag or world setting can set it for players: every user (GM included) runs this macro once on the browser they play on, then the scene redraws.
// Needs the permission "Use Script Macros" for players (Configure Permissions), or ask them to set Configure Settings > 3D Canvas > Shadow Quality = 4 by hand.
const MOD = "levels-3d-preview", WANT = 4;
if (!game.modules.get(MOD)?.active) return ui.notifications.warn("3D Canvas is not active.");
const cur = Number(game.settings.get(MOD, "shadowQuality"));
if (cur >= WANT) { ui.notifications.info("Shadow Quality is already " + cur + " on this browser."); return; }
await game.settings.set(MOD, "shadowQuality", WANT);
ui.notifications.info("Shadow Quality set to " + WANT + " (was " + cur + "). Redrawing the scene.");
await canvas.draw();
