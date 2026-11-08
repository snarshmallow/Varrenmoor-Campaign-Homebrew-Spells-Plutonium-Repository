// Pairing prompts for a relay's own console window (daemon.mjs --console and start.mjs): a loud banner for every request, and A = approve / D = deny / L = list keys.
// The facts (never a secret) always go to `out`; the banner and the keys only when `interactive`.
// Approving needs the code TYPED IN: A, the 6 digits shown on the Foundry screen, Enter. The code is deliberately never printed here, so the approver cannot just
// press a key for "whatever is oldest"; the request with the typed code is approved and nothing else.
export function attachPairingConsole(pairing, out, { interactive = false, stdin = process.stdin, onSigint } = {}) {
  const stamp = () => new Date().toISOString();
  if (!pairing.canEnable) return;
  pairing.on('request', (r) => {
    const warn = r.warnings || [];
    out(stamp(), `PAIRING REQUEST ${r.id}: "${r.name}" from ${r.ip}, origin ${r.origin || '(none)'}${warn.length ? ', WARNING: ' + warn.join('; ') : ''}`);
    if (interactive) out(['', '  ============ APPROVE THIS DEVICE? ============',
      `   Device : ${r.name}   (user ${r.userName || '?'}, world ${r.worldId || '?'})`,
      `   From   : ${r.ip}   origin ${r.origin || '(none)'}`,
      ...warn.map((w) => `   WARNING: ${w}`),
      '   The code is NOT shown here on purpose: read it from the Foundry screen.',
      '   Press  A, then TYPE the 6-digit code from the Foundry screen, then Enter   (D = deny)', '  ===============================================', ''].join(String.fromCharCode(10)));
  });
  for (const ev of ['approved', 'denied', 'revoked', 'expired']) pairing.on(ev, (x) => out(stamp(), `pairing ${ev}: ${x.name || x.id}`));
  pairing.on('config', (c) => out(stamp(), `pairing ${c.enabled ? 'ENABLED' : 'DISABLED'}, auto-request ${c.autoRequest ? 'on' : 'off'}`));
  if (interactive && stdin && stdin.isTTY) {
    stdin.setRawMode(true); stdin.resume();
    const CTRL_C = String.fromCharCode(3), ESC = String.fromCharCode(27), BS = String.fromCharCode(8), DEL = String.fromCharCode(127), CR = String.fromCharCode(13), LF = String.fromCharCode(10);
    let typing = null;       // null = normal mode; a string = the digits typed so far
    stdin.on('data', (b) => {
      const k = String(b).toLowerCase();
      if (k === CTRL_C) { onSigint && onSigint(); return; }
      if (typing !== null) {
        if (k === ESC) { typing = null; out(stamp(), 'approve cancelled'); return; }
        if (k === CR || k === LF) {
          const code = typing; typing = null;
          const hit = pairing.list().pending.find((x) => String(x.code) === code);
          if (!hit) { out(stamp(), 'no waiting request has that code (nothing approved)'); return; }
          const r = pairing.approve(hit.id, { days: 90, code });
          out(stamp(), r.status === 200 ? `approved "${hit.name}" from ${hit.ip}` : `approve failed: ${r.error || r.status}`);
          return;
        }
        if (k === BS || k === DEL) { typing = typing.slice(0, -1); return; }
        if (/^[0-9]$/.test(k) && typing.length < 6) { typing += k; out(stamp(), `code so far: ${'*'.repeat(typing.length)}${'_'.repeat(6 - typing.length)}`); }
        return;
      }
      const l = pairing.list();
      if (k === 'a') {
        if (!l.pending.length) { out(stamp(), 'no pairing request is waiting'); return; }
        typing = ''; out(stamp(), `type the 6-digit code shown on the Foundry screen, then Enter (Esc cancels). ${l.pending.length} request(s) waiting.`);
      } else if (k === 'd') {
        const first = l.pending[0]; if (!first) { out(stamp(), 'no pairing request is waiting'); return; }
        pairing.deny(first.id); out(stamp(), `denied "${first.name}" from ${first.ip}`);
      } else if (k === 'l') out(stamp(), `pairing ${l.enabled ? 'on' : 'OFF'}; paired devices: ${l.devices.map((d) => d.name).join(', ') || 'none'}; waiting: ${l.pending.length}`);
    });
  }
}
