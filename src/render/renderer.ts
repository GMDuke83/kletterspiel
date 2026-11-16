import * as THREE from 'three';

/** WebGL-Renderer mit Schatten und filmischem Tonemapping (WebGPU folgt spaeter). */
export function createRenderer(container: HTMLElement): THREE.WebGLRenderer {
  // Normaler Tiefenpuffer (am schnellsten, Early-Z bleibt aktiv). Der logarithmische Puffer kostete
  // spuerbar Leistung; mit Kamera-Nahgrenze 0,25 m reicht die Genauigkeit fuer km-Distanzen.
  // ?depth=log schaltet zum Vergleich den logarithmischen Puffer ein.
  const forceLog = new URLSearchParams(location.search).get('depth') === 'log';
  const renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: forceLog });
  // hochaufloesende Displays: hoechstens 1,5-fache Pixeldichte (sonst bis zu 4x so viele Pixel)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  container.appendChild(renderer.domElement);
  return renderer;
}
