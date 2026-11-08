// Pairing prompts for a relay's own console window (daemon.mjs --console and start.mjs): a loud banner for every request, and A = approve / D = deny / L = list keys.
// The facts (never a secret) always go to `out`; the banner and the keys only when `interactive`.
export function attachPairingConsole(pairing, out, { interactive = false, stdin = process.stdin, onSigint } = {}) {
  const stamp = () => new Date().toISOString();
  const spaced = (c) => String(c || '').replace(/(\d{3})(\d{3})/, '$1 $2');
  if (!pairing.canEnable) return;
  pairing.on('request', (r) => {
    out(stamp(), `PAIRING REQUEST ${r.id}: "${r.name}" from ${r.ip}, origin ${r.origin || '(none)'}, code ${spaced(r.code)}`);
    if (interactive) out(['', '  ============ APPROVE THIS DEVICE? ============',
      `   Device : ${r.name}   (user ${r.userName || '?'}, world ${r.worldId || '?'})`,
      `   From   : ${r.ip}   origin ${r.origin || '(none)'}${r.originMismatch ? '   WARNING: origin does not match what the device claims' : ''}`,
      `   Code   : ${spaced(r.code)}   (it must be the SAME code shown on the Foundry screen)`,
      '   Press  A = approve (90 days)   D = deny      (or use the Illustrator panel)', '  ===============================================', ''].join('\n'));
  });
  for (const ev of ['approved', 'denied', 'revoked', 'expired']) pairing.on(ev, (x) => out(stamp(), `pairing ${ev}: ${x.name || x.id}`));
  pairing.on('config', (c) => out(stamp(), `pairing ${c.enabled ? 'ENABLED' : 'DISABLED'}, auto-request ${c.autoRequest ? 'on' : 'off'}`));
  if (interactive && stdin && stdin.isTTY) {
    stdin.setRawMode(true); stdin.resume();
    stdin.on('data', (b) => {
      const k = String(b).toLowerCase();
      if (k === '\u0003') { onSigint && onSigint(); return; }
      const first = pairing.list().pending[0];
      if ((k === 'a' || k === 'd') && !first) { out(stamp(), 'no pairing request is waiting'); return; }
      if (k === 'a') out(stamp(), pairing.approve(first.id, { days: 90 }).status === 200 ? `approved "${first.name}" (${spaced(first.code)})` : 'approve failed');
      else if (k === 'd') { pairing.deny(first.id); }
      else if (k === 'l') { const l = pairing.list(); out(stamp(), `pairing ${l.enabled ? 'on' : 'OFF'}; paired devices: ${l.devices.map((d) => d.name).join(', ') || 'none'}; waiting: ${l.pending.length}`); }
    });
  }
}
