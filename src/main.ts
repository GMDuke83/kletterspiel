import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { createRenderer } from './render/renderer';
import { createEnvironment } from './world/environment';
import { loadWall } from './world/loadWall';

const renderer = createRenderer(document.body);
const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0xb7c8d8, 20, 60);

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.05, 2000);
camera.position.set(3.4, 2.1, 3.8);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 0.7, 0);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI * 0.495; // nicht unter den Boden
controls.update();

createEnvironment(scene, renderer);

const stats = document.getElementById('stats')!;
const showCol = document.getElementById('showCol') as HTMLInputElement;

loadWall(`${import.meta.env.BASE_URL}assets/test_rock.glb`)
  .then((wall) => {
    scene.add(wall.root);
    stats.textContent =
      `${wall.triangles} Dreiecke · ${wall.grips.length} Griffe · ` +
      `Kollision: ${wall.colliders.length} Mesh(es)`;
    showCol.addEventListener('change', () => {
      for (const c of wall.colliders) c.visible = showCol.checked;
    });
    document.body.dataset.loaded = 'true';
  })
  .catch((err: unknown) => {
    stats.textContent = `Fehler beim Laden: ${String(err)}`;
    document.body.dataset.loaded = 'error';
  });

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

renderer.setAnimationLoop(() => {
  controls.update();
  renderer.render(scene, camera);
});
