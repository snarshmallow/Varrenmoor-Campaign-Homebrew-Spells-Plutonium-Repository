// Module reconnect behaviour against a fake WebSocket: 4002 (replaced) stops auto-reconnect and warns once; other closes back off;
// "connected" notices are rate limited. Run: node --test foundry-bridge/module/reconnect.test.mjs
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

async function load() {
  const hooks = {}, notes = [], timers = [], sockets = [];
  const settings = { enabled: true, autoUrl: false, relayUrl: 'ws://127.0.0.1:1/module', token: 'x'.repeat(30), allowWrites: false };
  class FakeWS {
    constructor(url) { this.url = url; this.sent = []; sockets.push(this); }
    send(m) { this.sent.push(JSON.parse(m)); }
    close() {}
  }
  Object.assign(globalThis, {
    Hooks: { once: (n, f) => { hooks[n] = f; } },
    game: { settings: { register() {}, get: (m, k) => settings[k] }, user: { isGM: true }, modules: { get: () => ({ version: 'test' }) } },
    ui: { notifications: { info: (m) => notes.push(['info', m]), warn: (m) => notes.push(['warn', m]) } },
    WebSocket: FakeWS,
    setTimeout: (f, ms) => { timers.push({ f, ms }); return timers.length; },
    clearTimeout: () => {},
  });
  const src = fs.readFileSync(path.join(here, 'varrenmoor-bridge', 'scripts', 'bridge.js'), 'utf8');
  const tmp = path.join(os.tmpdir(), `bridge_rc_${Date.now()}_${Math.random().toString(36).slice(2)}.mjs`);
  fs.writeFileSync(tmp, src);
  await import(pathToFileURL(tmp).href);
  return { hooks, notes, timers, sockets };
}
const tick = () => new Promise((r) => process.nextTick(r));

test('4002 close: no reconnect timer, one warning; welcome notices are rate limited', async () => {
  const t = await load();
  await t.hooks.ready(); await tick(); await tick();
  assert.equal(t.sockets.length, 1);
  const ws = t.sockets[0];
  ws.onopen();
  assert.equal(ws.sent[0].type, 'hello');
  for (let i = 0; i < 5; i++) await ws.onmessage({ data: JSON.stringify({ type: 'welcome' }) });
  assert.equal(t.notes.filter((n) => /connected/.test(n[1])).length, 1, 'only one connected notice in a burst');
  const before = t.timers.length;
  ws.onclose({ code: 4002 });
  assert.equal(t.timers.length, before, 'no reconnect scheduled after 4002');
  assert.equal(t.notes.filter((n) => n[0] === 'warn').length, 1);
  assert.match(t.notes.at(-1)[1], /another GM tab/);
  ws.onclose({ code: 4002 });
  assert.equal(t.notes.filter((n) => n[0] === 'warn').length, 1, 'warning is rate limited too');
});

test('ordinary close backs off and reconnects', async () => {
  const t = await load();
  await t.hooks.ready(); await tick(); await tick();
  const ws = t.sockets[0];
  ws.onclose({ code: 1006 });
  assert.equal(t.timers.at(-1).ms, 1000);
  const ws2 = (await (async () => { await t.timers.at(-1).f(); await tick(); await tick(); return t.sockets.at(-1); })());
  assert.notEqual(ws2, ws);
  ws2.onclose({ code: 1006 });
  assert.equal(t.timers.at(-1).ms, 2000);
});
