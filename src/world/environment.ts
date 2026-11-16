import * as THREE from 'three';
import { Sky } from 'three/addons/objects/Sky.js';

export interface EnvironmentOptions {
  /** Bodenebene bei y = 0 (nur ohne echtes Gelaende) */
  ground?: boolean;
  /** Dunst fuer Fernsicht (km-Distanzen) */
  haze?: boolean;
  /** Sonnenstand: Richtung (Grad, 0 = +Z/Sueden, 90 = +X/Osten, -90 = Westen) und Hoehe ueber Horizont */
  sunAzimuthDeg?: number;
  sunElevationDeg?: number;
}

export interface Environment {
  sun: THREE.DirectionalLight;
  /** Himmel mit der Kamera mitfuehren, Schatten um den Fokuspunkt halten */
  update(camera: THREE.Camera, focus: THREE.Vector3): void;
}

/** Himmel, Sonne mit Schatten, Umgebungslicht, optional Boden und Dunst. */
export function createEnvironment(
  scene: THREE.Scene,
  renderer: THREE.WebGLRenderer,
  opts: EnvironmentOptions = { ground: true },
): Environment {
  const elevation = opts.sunElevationDeg ?? 32; // Grad ueber dem Horizont
  const azimuth = opts.sunAzimuthDeg ?? 25; // Standard: vorne-rechts, die Testwand schaut nach +Z
  const sunDir = new THREE.Vector3().setFromSphericalCoords(
    1,
    THREE.MathUtils.degToRad(90 - elevation),
    THREE.MathUtils.degToRad(azimuth),
  );

  const sky = new Sky();
  sky.scale.setScalar(30000);
  const u = sky.material.uniforms;
  u['turbidity'].value = 3; // klare Hochgebirgsluft
  u['rayleigh'].value = 1.2;
  u['mieCoefficient'].value = 0.004;
  u['mieDirectionalG'].value = 0.8;
  u['sunPosition'].value.copy(sunDir);
  scene.add(sky);

  // Himmel als Umgebungs-Reflexion (IBL) fuer PBR-Materialien
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envScene = new THREE.Scene();
  const envSky = sky.clone();
  envSky.scale.setScalar(1000);
  envScene.add(envSky);
  scene.environment = pmrem.fromScene(envScene).texture;
  scene.environmentIntensity = 0.2;

  if (opts.haze) {
    // leichter blaugrauer Dunst: Berge in 5-10 km Entfernung werden heller und blasser
    scene.fog = new THREE.FogExp2(0xc4d2e2, 0.00007);
  }

  const sun = new THREE.DirectionalLight(0xfff4e6, 3.0);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.bias = -0.0005;
  sun.shadow.normalBias = 0.02;
  const cam = sun.shadow.camera;
  cam.left = cam.bottom = -12;
  cam.right = cam.top = 12;
  cam.near = 1;
  cam.far = 80;
  scene.add(sun, sun.target);

  scene.add(new THREE.HemisphereLight(0xf2f0ea, 0x6b5a48, 0.6));

  if (opts.ground) {
    const ground = new THREE.Mesh(
      new THREE.CircleGeometry(400, 64),
      new THREE.MeshStandardMaterial({ color: 0x6f6250, roughness: 1 }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);
  }

  return {
    sun,
    update(camera, focus) {
      sky.position.copy(camera.position);
      sun.target.position.copy(focus);
      sun.position.copy(focus).addScaledVector(sunDir, 40);
    },
  };
}
