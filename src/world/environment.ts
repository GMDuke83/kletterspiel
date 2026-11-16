import * as THREE from 'three';
import { Sky } from 'three/addons/objects/Sky.js';

/** Himmel, Sonne mit Schatten, Umgebungslicht und Bodenebene. */
export function createEnvironment(scene: THREE.Scene, renderer: THREE.WebGLRenderer): void {
  const elevation = 35; // Grad ueber dem Horizont
  const azimuth = 140;
  const sunDir = new THREE.Vector3().setFromSphericalCoords(
    1,
    THREE.MathUtils.degToRad(90 - elevation),
    THREE.MathUtils.degToRad(azimuth),
  );

  const sky = new Sky();
  sky.scale.setScalar(1000);
  const u = sky.material.uniforms;
  u['turbidity'].value = 6;
  u['rayleigh'].value = 1.5;
  u['mieCoefficient'].value = 0.005;
  u['mieDirectionalG'].value = 0.8;
  u['sunPosition'].value.copy(sunDir);
  scene.add(sky);

  // Himmel als Umgebungs-Reflexion (IBL) fuer PBR-Materialien
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envScene = new THREE.Scene();
  envScene.add(sky.clone());
  scene.environment = pmrem.fromScene(envScene).texture;
  scene.environmentIntensity = 0.3;

  const sun = new THREE.DirectionalLight(0xfff1dc, 2.8);
  sun.position.copy(sunDir).multiplyScalar(10);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.bias = -0.0005;
  sun.shadow.normalBias = 0.02;
  const cam = sun.shadow.camera;
  cam.left = cam.bottom = -4;
  cam.right = cam.top = 4;
  cam.near = 1;
  cam.far = 25;
  scene.add(sun);

  scene.add(new THREE.HemisphereLight(0xe6ecf5, 0x5b4c3c, 0.45));

  const ground = new THREE.Mesh(
    new THREE.CircleGeometry(40, 64),
    new THREE.MeshStandardMaterial({ color: 0x6f6250, roughness: 1 }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);
}
