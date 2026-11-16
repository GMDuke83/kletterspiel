import * as THREE from 'three';
import { createRenderer } from './render/renderer';
import { createEnvironment } from './world/environment';
import { loadWall } from './world/loadWall';
import { Climber, type Side } from './climbing/climber';
import { GripAim } from './climbing/aim';
import { PlaceholderFigure } from './character/placeholder';
import { CameraRig } from './core/cameraRig';
import { Hud } from './ui/hud';
import { Autopilot } from './climbing/autopilot';

const BASE = import.meta.env.BASE_URL;

const renderer = createRenderer(document.body);
const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0xc9d5e0, 40, 220);
const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.05, 3000);
camera.position.set(0, 3, 8);
createEnvironment(scene, renderer);

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

async function start(): Promise<void> {
  const [wall, rock] = await Promise.all([
    loadWall(`${BASE}assets/test_wall.glb`),
    loadWall(`${BASE}assets/test_rock.glb`),
  ]);
  scene.add(wall.root);
  rock.root.position.set(4.6, 0, 2.2);
  rock.root.rotation.y = 0.6;
  rock.root.traverse((o) => {
    if (o.name.startsWith('grip_')) o.visible = false;
  });
  scene.add(rock.root);

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

  const climber = new Climber(wall.grips, probe);
  const figure = new PlaceholderFigure();
  scene.add(figure.group);
  const aim = new GripAim(wall.grips, scene, renderer.domElement);
  const rig = new CameraRig(camera, renderer.domElement);
  const hud = new Hud();
  document.getElementById('loading')!.remove();

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

  // fuer automatische Tests (Headless-Screenshot)
  (window as unknown as { __game: unknown }).__game = { climber, wall, aim };
  document.body.dataset.loaded = 'true';

  const params = new URLSearchParams(location.search);
  const autopilot = params.has('autoclimb') ? new Autopilot(climber, wall.grips) : null;
  // ?autoclimb=8 -> nach 8 s Spielzeit anhalten (fuer Screenshots auf halber Hoehe)
  const stopAfter = Number(params.get('autoclimb')) || Infinity;

  // ?sim=30 -> 30 s Autopilot sofort durchrechnen (Test ohne Echtzeit, z. B. fuer Headless-Screenshots)
  const sim = Number(params.get('sim'));
  if (sim > 0) {
    const ap = new Autopilot(climber, wall.grips);
    for (let t = 0; t < sim && climber.state !== 'summit'; t += 1 / 60) {
      ap.update(1 / 60);
      climber.update(1 / 60);
    }
    const hs = (['left', 'right'] as const)
      .map((s) => {
        const h = climber.hands[s];
        const g = h.grip ?? h.target;
        return `${s}:${g ? g.name : '-'}@${h.pos.toArray().map((v) => v.toFixed(2)).join(',')}`;
      })
      .join(' ');
    const result = `sim ${sim}s: Zustand=${climber.state} Höhe=${climber.height.toFixed(1)}m Zeit=${climber.elapsed.toFixed(1)}s Stürze=${climber.falls} body=${climber.body.toArray().map((v) => v.toFixed(2)).join(',')} ${hs}`;
    console.log(result);
    document.title = result;
    rig.distance = 5;
  }

  const clock = new THREE.Clock();
  renderer.setAnimationLoop(() => {
    const dt = Math.min(clock.getDelta(), 0.05);
    if (autopilot && climber.elapsed < stopAfter) autopilot.update(dt);
    climber.update(dt);
    figure.update(climber, clock.elapsedTime);
    rig.update(climber.body, climber.out, dt);
    aim.update(camera, window.innerWidth, window.innerHeight, reachable);
    hud.update(climber, aim.hovered, aim.hovered ? reachable(aim.hovered) : false);
    renderer.render(scene, camera);
  });
}

start().catch((err: unknown) => {
  const l = document.getElementById('loading');
  if (l) l.textContent = `Fehler beim Laden: ${String(err)}`;
  document.body.dataset.loaded = 'error';
  console.error(err);
});
