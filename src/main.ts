import * as THREE from 'three';
import { createRenderer } from './render/renderer';
import { createEnvironment } from './world/environment';
import { loadWall } from './world/loadWall';
import { loadTerrain } from './world/terrain';
import { Climber, type Side } from './climbing/climber';
import { GripAim } from './climbing/aim';
import { PlaceholderFigure } from './character/placeholder';
import { CameraRig } from './core/cameraRig';
import { Hud } from './ui/hud';
import { Autopilot } from './climbing/autopilot';
import route from './routes/dufourspitze.json';

const BASE = import.meta.env.BASE_URL;
const params = new URLSearchParams(location.search);
/** ?noterrain -> nur Testwand ohne Gelaende (schneller Start) */
const useTerrain = !params.has('noterrain');

const renderer = createRenderer(document.body);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.05, 40000);
const env = createEnvironment(
  scene,
  renderer,
  useTerrain
    ? // Sommerabend: Sonne aus West-Nordwest streift die Nordwand
      { ground: false, haze: true, sunAzimuthDeg: -112, sunElevationDeg: 22 }
    : { ground: true },
);

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

const loadingEl = document.getElementById('loading')!;
const progress = { wall: 0, terrain: useTerrain ? 0 : 1 };
function showProgress(): void {
  const p = useTerrain ? progress.wall * 0.15 + progress.terrain * 0.85 : progress.wall;
  loadingEl.textContent = `lade ${useTerrain ? 'Dufourspitze' : 'Wand'} … ${Math.round(p * 100)} %`;
}

async function start(): Promise<void> {
  showProgress();
  const wallPlace = useTerrain
    ? { position: route.wall.position as THREE.Vector3Tuple, yaw: route.wall.yaw }
    : {};
  const [wall, terrain] = await Promise.all([
    loadWall(`${BASE}assets/test_wall.glb`, wallPlace, (f) => {
      progress.wall = f;
      showProgress();
    }),
    useTerrain
      ? loadTerrain(`${BASE}${route.terrain.file}`, renderer, (f) => {
          progress.terrain = f;
          showProgress();
        })
      : Promise.resolve(null),
  ]);
  scene.add(wall.root);
  if (terrain) scene.add(terrain);
  const groundY = useTerrain ? route.wall.position[1] : 0;

  if (useTerrain) {
    // kleiner Felsabsatz am Wandfuss (das Gelaende faellt davor steil ab)
    const ledge = new THREE.Mesh(
      new THREE.BoxGeometry(6.4, 2.0, 2.2),
      new THREE.MeshStandardMaterial({ color: 0x55524e, roughness: 0.95 }),
    );
    ledge.position.set(0, -1.0, 0.7);
    ledge.castShadow = ledge.receiveShadow = true;
    wall.root.add(ledge);
  }

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
  const figure = new PlaceholderFigure();
  scene.add(figure.group);
  const aim = new GripAim(wall.grips, scene, renderer.domElement);
  const rig = new CameraRig(camera, renderer.domElement);
  if (useTerrain) {
    // schraeg von der Seite: Wand und Landschaft gleichzeitig im Bild
    rig.defaultYaw = rig.yaw = 0.65;
    rig.distance = 5.5;
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
  let fpsTime = 0;
  const clock = new THREE.Clock();
  (window as unknown as { __game: unknown }).__game = { climber, wall, aim, rig };
  document.body.dataset.loaded = 'true';

  renderer.setAnimationLoop(() => {
    const dt = Math.min(clock.getDelta(), 0.05);
    if (autopilot && climber.elapsed < stopAfter) autopilot.update(dt);
    climber.update(dt);
    figure.update(climber, clock.elapsedTime);
    rig.update(climber.body, climber.out, dt);
    env.update(camera, climber.body);
    aim.update(camera, window.innerWidth, window.innerHeight, reachable);
    hud.update(climber, aim.hovered, aim.hovered ? reachable(aim.hovered) : false, climber.body.y);
    renderer.render(scene, camera);
    frames++;
    fpsTime += dt;
    if (fpsTime >= 1) {
      document.body.dataset.fps = String(Math.round(frames / fpsTime));
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
