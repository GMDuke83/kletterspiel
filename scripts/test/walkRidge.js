// Im Browser (per CDP) ausgefuehrt: geht den markierten Gratweg vom Wandausstieg bis zum Gipfel
// und schreibt das Ergebnis in document.title. Benutzt die echte Walker-Logik und das echte Gelaende.
(() => {
  const g = window.__game;
  const w = g.walker;
  w.place(g.exitPt.clone(), 0);
  let falls = 0, t = 0, idx = 1, stuck = 0, last = w.pos.clone();
  const pts = g.ridge;
  while (idx < pts.length && t < 600) {
    const [x, , z] = pts[idx];
    const dx = x - w.pos.x, dz = z - w.pos.z;
    if (Math.hypot(dx, dz) < 1.0) { idx++; continue; }
    w.yaw = Math.atan2(-dx, -dz);
    const drop = w.update(1 / 30, { forward: 1, strafe: 0, run: false, jump: false }, 1);
    if (drop > 4) { falls++; w.place(w.safe.clone(), w.yaw); }
    w.stamina = Math.max(w.stamina, 0.3); // Test: Puste nicht als Abbruchgrund
    t += 1 / 30;
    if (Math.floor(t) !== Math.floor(t - 1 / 30)) {
      if (w.pos.distanceTo(last) < 0.05) stuck++; else stuck = 0;
      last.copy(w.pos);
      if (stuck > 8) break;
    }
  }
  const toSummit = Math.hypot(w.pos.x - g.summitPt.x, w.pos.z - g.summitPt.z);
  document.title = `GEHTEST ${toSummit < 3 ? 'BESTANDEN' : 'NICHT BESTANDEN'}: ${t.toFixed(0)} s, Stuerze ${falls}, Punkt ${idx}/${pts.length}, Rest ${toSummit.toFixed(1)} m, Gelaende ${w.terrain}`;
})();
