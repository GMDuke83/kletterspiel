// Test gegen Bein-Zucken (im echten Browser, mit Grafikkarte):
//   node scripts/test/footStability.mjs [url]
// Laedt das Spiel, laesst den Autopiloten 4 s klettern und dann stillhalten,
// misst Fuss- und Kniepositionen ueber 5 s. Erlaubt: hoechstens 1 cm Bewegung.
import { spawn } from 'node:child_process';

const url = process.argv[2] ?? 'http://localhost:5173/?figure=human&autoclimb=4';
const edge = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const prof = 'D:\\kletterspiel\\.cache\\edgetest';
const p = spawn(edge, ['--headless=new', '--remote-debugging-port=9334', `--user-data-dir=${prof}`,
  '--use-angle=d3d11', '--enable-gpu', '--ignore-gpu-blocklist', '--window-size=1280,720', 'about:blank']);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
await sleep(2500);
const page = (await (await fetch('http://127.0.0.1:9334/json')).json()).find((t) => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0;
const pending = new Map();
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) pending.get(m.id)(m.result);
};
await new Promise((r) => (ws.onopen = r));
const call = (method, params = {}) =>
  new Promise((res) => {
    const i = ++id;
    pending.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params }));
  });
const evaluate = async (expr) => (await call('Runtime.evaluate', { expression: expr, returnByValue: true })).result.value;

await call('Page.navigate', { url });
for (let i = 0; i < 60 && (await evaluate('document.body.dataset.loaded')) !== 'true'; i++) await sleep(500);
await sleep(9000); // klettern lassen, dann steht der Autopilot still
const probe = `(() => {
  const f = window.__game.figure; if (!f) return null;
  const out = {};
  for (const s of ['left','right']) { const p = f.feet[s].planted; out['foot_'+s] = p ? [p.x,p.y,p.z] : null; }
  for (const b of ['calf_l','calf_r','shin.L','shin.R']) {
    let bone = null; f.root.traverse(o => { if (o.isBone && (o.name === b || o.name === b.replace('.',''))) bone = o; });
    if (bone) { bone.updateWorldMatrix(true,false); const e = bone.matrixWorld.elements; out['knee_'+b] = [e[12],e[13],e[14]]; }
  }
  const c = window.__game.climber; out.body = [c.body.x, c.body.y, c.body.z];
  out.hands = [c.hands.left.pos.x + c.hands.right.pos.x, c.hands.left.pos.y + c.hands.right.pos.y, 0];
  out.state = c.state; out.h = c.height;
  return out;
})()`;
const a = await evaluate(probe);
let maxMove = 0;
let bodyMoved = 0;
let worst = '';
for (let k = 0; k < 10; k++) {
  await sleep(500);
  const b = await evaluate(probe);
  for (const key of Object.keys(a)) {
    if (!Array.isArray(a[key]) || !Array.isArray(b[key])) continue;
    if (key === 'body' || key === 'hands') {
      const db = Math.hypot(a[key][0] - b[key][0], a[key][1] - b[key][1], a[key][2] - b[key][2]);
      if (db > 0.005) bodyMoved = Math.max(bodyMoved, db);
      continue;
    }
    const d = Math.hypot(a[key][0] - b[key][0], a[key][1] - b[key][1], a[key][2] - b[key][2]);
    if (d > maxMove) {
      maxMove = d;
      worst = key;
    }
  }
}
if (bodyMoved) console.log(`Hinweis: Koerper/Haende bewegten sich selbst um ${(bodyMoved * 100).toFixed(1)} cm (Mechanik, z. B. Ausdauer/Abrutschen) - Messung nicht aussagekraeftig`);
console.log(`Zustand ${a?.state}, Hoehe ${a?.h?.toFixed(2)} m; groesste Bewegung in 5 s: ${(maxMove * 100).toFixed(2)} cm (${worst})`);
const verdict = bodyMoved ? 'UNGUELTIG (Figur war nicht in Ruhe)' : maxMove <= 0.01 ? 'BESTANDEN' : 'NICHT BESTANDEN';
console.log(verdict);
ws.close();
p.kill();
process.exit(verdict === 'NICHT BESTANDEN' ? 1 : 0);
