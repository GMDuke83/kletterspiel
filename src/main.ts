import * as THREE from 'three';
import { createRenderer } from './render/renderer';
import { createEnvironment } from './world/environment';
import { loadWall } from './world/loadWall';
import { loadTerrain, makeHeightSampler } from './world/terrain';
import { applyRockPhoto } from './render/rockPhotoMaterial';
import { Climber, type Side } from './climbing/climber';
import { GripAim } from './climbing/aim';
import { PlaceholderFigure } from './character/placeholder';
import { ClimberFigure } from './character/climberFigure';
import { CameraRig } from './core/cameraRig';
import { Hud } from './ui/hud';
import { Autopilot } from './climbing/autopilot';
import route from './routes/dufourspitze.json';

const BASE = import.meta.env.BASE_URL;
const params = new URLSearchParams(location.search);
/** ?noterrain -> nur Testwand ohne Gelaende (schneller Start) */
const useTerrain = !params.has('noterrain');

// Qualitaet: "hoch" (Nahbereich 10 cm, Detail-Shader, grosse Schatten) oder "niedrig"
function readQuality(): 'high' | 'low' {
  const q = params.get('q');
  if (q === 'low' || q === 'high') return q;
  try {
    return localStorage.getItem('quality') === 'low' ? 'low' : 'high';
  } catch {
    return 'high';
  }
}
const quality = readQuality();
const high = quality === 'high';

const renderer = createRenderer(document.body);
if (!high) renderer.setPixelRatio(1);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.25, 40000);
const env = createEnvironment(
  scene,
  renderer,
  useTerrain
    ? // Sommerabend: Sonne aus West-Nordwest streift die Nordwand
      { ground: false, haze: true, sunAzimuthDeg: -112, sunElevationDeg: 22, shadowMapSize: high ? 2048 : 1024 }
    : { ground: true },
);

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// Qualitaets-Schalter im HUD
const qBtn = document.getElementById('quality') as HTMLButtonElement;
qBtn.textContent = `Qualität: ${high ? 'hoch' : 'niedrig'}`;
qBtn.addEventListener('click', () => {
  try {
    localStorage.setItem('quality', high ? 'low' : 'high');
  } catch {
    /* ohne Speicher: nur per ?q=low */
  }
  const u = new URL(location.href);
  u.searchParams.set('q', high ? 'low' : 'high');
  location.href = u.toString();
});

const loadingEl = document.getElementById('loading')!;
const progress: Record<string, number> = {};
const weights: Record<string, number> = useTerrain
  ? { wall: 0.1, terrain: 0.55, near: high ? 0.35 : 0.05 }
  : { wall: 1 };
function onProgress(key: string) {
  return (f: number) => {
    progress[key] = f;
    let p = 0;
    for (const k in weights) p += (progress[k] ?? 0) * weights[k];
    const total = Object.values(weights).reduce((a, b) => a + b, 0);
    loadingEl.textContent = `lade ${useTerrain ? 'Dufourspitze' : 'Wand'} … ${Math.round((p / total) * 100)} %`;
  };
}

async function start(): Promise<void> {
  onProgress('wall')(0);
  const wallPlace = useTerrain
    ? { position: route.wall.position as THREE.Vector3Tuple, yaw: route.wall.yaw }
    : {};
  const o = route.origin;
  const detail = high && useTerrain && !params.has('nodetail')
    ? {
        // Struktur aus der CC0-Fels-Fototextur (Poly Haven "Rock Face 03")
        detail: await new THREE.TextureLoader().loadAsync(`${BASE}assets/rock_detail.jpg`),
        tileSize: 4,
        bump: params.has('bump') ? Number(params.get('bump')) : undefined,
        albedo: params.has('albedo') ? Number(params.get('albedo')) : undefined,
        bounds: {
          minX: route.bounds.E0 - o.E,
          maxX: route.bounds.E1 - o.E,
          minZ: -(route.bounds.N1 - o.N),
          maxZ: -(route.bounds.N0 - o.N),
        },
      }
    : null;
  const [wall, terrain, near] = await Promise.all([
    loadWall(`${BASE}${useTerrain ? route.wall.file : 'assets/test_wall.glb'}`, wallPlace, onProgress('wall')),
    useTerrain ? loadTerrain(`${BASE}${route.terrain.file}`, renderer, detail, onProgress('terrain')) : null,
    useTerrain
      ? loadTerrain(`${BASE}${high ? route.near.file : route.near.fileLow}`, renderer, detail, onProgress('near'))
      : null,
  ]);
  scene.add(wall.root);
  if (terrain) scene.add(terrain);

  if (useTerrain) {
    // Fels-Fototextur (CC0) auf der Kletterwand: Struktur, Normalen und Rauheit
    const tl = new THREE.TextureLoader();
    const [detailT, normalT, roughT] = await Promise.all(
      ['rock_detail.jpg', 'rock_normal.jpg', 'rock_rough.jpg'].map((f) => tl.loadAsync(`${BASE}assets/${f}`)),
    );
    const [w, h] = route.wall.size;
    const tile = 2.5; // Meter pro Kachel
    wall.root.traverse((m) => {
      if (m instanceof THREE.Mesh && m.name === 'wall') {
        applyRockPhoto(m.material as THREE.MeshStandardMaterial, { detail: detailT, normal: normalT, rough: roughT },
          new THREE.Vector2(w / tile, h / tile), high ? 1 : 0.7);
      }
    });
  }
  if (near) scene.add(near);
  const groundY = useTerrain ? route.wall.position[1] : 0;

  // Abstand zur Wand messen (Raycast gegen die sichtbaren Wand-Meshes)
  const ray = new THREE.Raycaster();
  const origin = new THREE.Vector3();
  const back = new THREE.Vector3();
  const probe = (p: THREE.Vector3, out: THREE.Vector3): number | null => {
    origin.copy(p).addScaledVector(out, 2.5);
    ray.set(origin, back.copy(out).negate());
    ray.far = 5;
    const hit = ray.intersectObjects(wall.surfaces, false)[0];
    return hit ? hit.distance - 2.5 : null;
  };

  const climber = new Climber(wall.grips, probe, groundY);
  // eigene Kletterfigur (scripts/blender/make_climber.py); bei Ladefehler der alte Platzhalter
  let figure: ClimberFigure | null = null;
  let placeholder: PlaceholderFigure | null = null;
  try {
    // realistische Figur (MPFB/MakeHuman, CC0) noch in Arbeit: nur mit ?figure=human
    const simple = params.get('figure') !== 'human';
    figure = await ClimberFigure.load(`${BASE}assets/${simple ? 'climber.glb' : 'climber_human.glb'}`);
    figure.footholds = wall.feet;
    scene.add(figure.root);
  } catch (err) {
    console.warn('Kletterfigur nicht geladen, nutze Platzhalter', err);
    placeholder = new PlaceholderFigure();
    scene.add(placeholder.group);
  }
  const aim = new GripAim(wall.grips, scene, renderer.domElement);
  // Hilfe "Griffe anzeigen" (Standard an), gespeichert im Browser
  const showGrips = document.getElementById('showGrips') as HTMLInputElement;
  try {
    showGrips.checked = localStorage.getItem('showGrips') !== '0';
  } catch {
    showGrips.checked = true;
  }
  aim.showMarkers = showGrips.checked;
  showGrips.addEventListener('change', () => {
    aim.showMarkers = showGrips.checked;
    try {
      localStorage.setItem('showGrips', showGrips.checked ? '1' : '0');
    } catch {
      /* egal */
    }
  });
  const rig = new CameraRig(camera, renderer.domElement);
  if (useTerrain) {
    // schraeg von der Seite: Wand und Landschaft gleichzeitig im Bild
    rig.defaultYaw = rig.yaw = 0.65;
    rig.distance = 5.5;
    if (near) {
      const nb = route.near.bounds;
      const step = high ? route.near.meshStep : 3.6;
      rig.ground = makeHeightSampler(near, nb.E0 - o.E, -(nb.N1 - o.N), step, nb.E1 - nb.E0);
    }
  }
  const hud = new Hud();
  loadingEl.remove();

  const reachable = (g: (typeof wall.grips)[number]) => climber.canReach('left', g) || climber.canReach('right', g);
  const grab = (side: Side) => {
    if (aim.hovered) climber.grab(side, aim.hovered);
  };

  renderer.domElement.addEventListener('contextmenu', (e) => e.preventDefault());
  renderer.domElement.addEventListener('pointerdown', (e) => {
    if (e.button === 0) grab('left');
    if (e.button === 2) grab('right');
  });
  window.addEventListener('keydown', (e) => {
    const k = e.key.toLowerCase();
    if (k === 'q') grab('left');
    if (k === 'e') grab('right');
    if (k === 'r') climber.reset(true);
  });

  const autopilot = params.has('autoclimb') ? new Autopilot(climber, wall.grips) : null;
  const stopAfter = Number(params.get('autoclimb')) || Infinity;

  // ?sim=30 -> 30 s Autopilot sofort durchrechnen (Test ohne Echtzeit, z. B. fuer Headless-Screenshots)
  const sim = Number(params.get('sim'));
  if (sim > 0) {
    const ap = new Autopilot(climber, wall.grips);
    for (let t = 0; t < sim && climber.state !== 'summit'; t += 1 / 60) {
      ap.update(1 / 60);
      climber.update(1 / 60);
    }
    document.title = `sim ${sim}s: ${climber.state} Höhe=${climber.height.toFixed(1)}m Stürze=${climber.falls}`;
    rig.distance = 5;
  }
  if (params.has('dist')) rig.distance = Number(params.get('dist'));
  if (params.has('pitch')) rig.pitch = Number(params.get('pitch'));
  if (params.has('yaw')) rig.yaw = Number(params.get('yaw'));
  // ?view=valley -> Aussicht ins Tal (wie Taste V), ?view=side -> Kamera seitlich und weit weg
  if (params.get('view') === 'valley') rig.lookout = true;
  if (params.get('view') === 'side') {
    rig.yaw = 1.3;
    rig.pitch = 0.35;
    rig.distance = 25;
  }

  // Bildrate messen (fuer Tests in document.body.dataset.fps)
  const fpsEl = document.getElementById('fps')!;
  let frames = 0;
  let lastT = 0;
  let slow = 0;
  let reduced = false;
  let fpsTime = 0;
  const clock = new THREE.Clock();
  (window as unknown as { __game: unknown }).__game = { climber, wall, aim, rig };
  document.body.dataset.loaded = 'true';

  renderer.setAnimationLoop(() => {
    const dt = Math.min(clock.getDelta(), 0.05);
    if (autopilot && climber.elapsed < stopAfter) autopilot.update(dt);
    climber.update(dt);
    if (figure) {
      const moving = climber.hands.left.target ?? climber.hands.right.target;
      const look = moving?.position ?? aim.hovered?.position ?? null;
      figure.update(climber, clock.elapsedTime, dt, probe, groundY, look);
    }
    placeholder?.update(climber, clock.elapsedTime);
    rig.update(climber.body, climber.out, dt);
    env.update(camera, climber.body);
    aim.update(camera, window.innerWidth, window.innerHeight, reachable);
    hud.update(climber, aim.hovered, aim.hovered ? reachable(aim.hovered) : false, useTerrain ? climber.body.y : NaN);
    renderer.render(scene, camera);
    frames++;
    const now = performance.now() / 1000; // nicht clock.getElapsedTime(): das verstellt getDelta()
    fpsTime += lastT ? now - lastT : 0;
    lastT = now;
    if (fpsTime >= 1) {
      const fps = frames / fpsTime;
      // automatische Anpassung: 3 Sekunden in Folge unter 45 FPS -> Pixeldichte und Schatten reduzieren
      slow = fps < 45 ? slow + 1 : 0;
      if (slow >= 3 && !reduced) {
        reduced = true;
        renderer.setPixelRatio(1);
        env.sun.shadow.mapSize.set(1024, 1024);
        env.sun.shadow.map?.dispose();
        env.sun.shadow.map = null;
        climber.say('Grafik automatisch reduziert (Bildrate)');
      }
      document.body.dataset.fps = String(Math.round(fps));
      fpsEl.textContent = `${document.body.dataset.fps} FPS`;
      frames = 0;
      fpsTime = 0;
    }
  });
}

start().catch((err: unknown) => {
  loadingEl.textContent = `Fehler beim Laden: ${String(err)}`;
  document.body.dataset.loaded = 'error';
  console.error(err);
});
