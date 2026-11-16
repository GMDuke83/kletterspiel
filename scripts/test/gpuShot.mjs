// GPU-Screenshot/Pruefung im unsichtbaren Edge: GPU=1 PROFILE=<ordner> [EVAL=<js>] node scripts/test/gpuShot.mjs <url> <png>
// Minimaler CDP-Client: oeffnet URL in headless Edge und gibt Konsole + Exceptions aus.
import { spawn } from 'node:child_process';
const url = process.argv[2];
const edge = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const prof = process.env.TEMP + '\\cdpprof';
const p = spawn(edge, ['--headless=new', '--remote-debugging-port=9333', `--user-data-dir=${prof}`,
  ...(process.env.GPU ? ['--use-angle=d3d11', '--enable-gpu', '--ignore-gpu-blocklist', '--enable-gpu-rasterization']
                      : ['--enable-unsafe-swiftshader', '--use-angle=swiftshader']),
  `--window-size=${process.env.SIZE || '1280,720'}`, 'about:blank']);
await new Promise((r) => setTimeout(r, 2500));
const targets = await (await fetch('http://127.0.0.1:9333/json')).json();
const page = targets.find((t) => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0;
const send = (method, params = {}) => ws.send(JSON.stringify({ id: ++id, method, params }));
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.method === 'Runtime.consoleAPICalled') console.log('console.' + m.params.type, m.params.args.map((a) => a.value ?? a.description).join(' '));
  if (m.method === 'Runtime.exceptionThrown') console.log('EXCEPTION', m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text);
  if (m.method === 'Log.entryAdded') console.log('log', m.params.entry.level, m.params.entry.text, m.params.entry.url ?? '');
};
await new Promise((r) => (ws.onopen = r));
send('Runtime.enable');
send('Log.enable');
send('Page.navigate', { url });
await new Promise((r) => setTimeout(r, Number(process.env.WAIT || 20000)));
if (process.env.EVAL) {
  send('Runtime.evaluate', { expression: process.env.EVAL });
  await new Promise((r) => setTimeout(r, Number(process.env.EVALWAIT || 2500)));
}
send('Runtime.evaluate', { expression: `(function(){var r='no gl';try{var c=document.createElement('canvas').getContext('webgl2');var e=c.getExtension('WEBGL_debug_renderer_info');r=c.getParameter(e.UNMASKED_RENDERER_WEBGL);}catch(x){} var l=document.getElementById('loading'); return r+' | '+document.querySelectorAll('canvas').length+' canvas, loaded='+document.body.dataset.loaded+', fps='+document.body.dataset.fps+', '+document.title+' | '+(l?l.textContent:'');})()`, returnByValue: true });
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data);
  if (m.result?.result?.value) console.log('STATE', m.result.result.value);
});
send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 720, deviceScaleFactor: 1, mobile: false });
await new Promise((r) => setTimeout(r, 3000));
const shotId = id + 1;
send('Page.captureScreenshot', { format: 'png' });
await new Promise((resolve) => ws.addEventListener('message', async (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id === shotId && m.result?.data) {
    (await import('node:fs')).writeFileSync(process.argv[3], Buffer.from(m.result.data, 'base64'));
    console.log('SCREENSHOT', process.argv[3]);
    resolve();
  }
}));
ws.close();
p.kill();
process.exit(0);
