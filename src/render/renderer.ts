import * as THREE from 'three';

/** WebGL-Renderer mit Schatten und filmischem Tonemapping (WebGPU folgt spaeter). */
export function createRenderer(container: HTMLElement): THREE.WebGLRenderer {
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    preserveDrawingBuffer: true,
    logarithmicDepthBuffer: true, // Gelaende bis viele km entfernt ohne Z-Flimmern
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  container.appendChild(renderer.domElement);
  return renderer;
}
