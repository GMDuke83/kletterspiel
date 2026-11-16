import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

/**
 * Laedt das Gelaende-GLB (aus scripts/terrain/build_terrain.py).
 * Koordinaten: x = Osten, y = Hoehe ueber Meer, z = Sueden (Meter, 1:1).
 */
export async function loadTerrain(
  url: string,
  renderer: THREE.WebGLRenderer,
  onProgress?: (fraction: number) => void,
): Promise<THREE.Object3D> {
  const gltf = await new GLTFLoader().loadAsync(url, (e) => {
    if (onProgress && e.total) onProgress(e.loaded / e.total);
  });
  const maxAniso = renderer.capabilities.getMaxAnisotropy();
  gltf.scene.traverse((o) => {
    if (o instanceof THREE.Mesh) {
      o.receiveShadow = true;
      const mat = o.material as THREE.MeshStandardMaterial;
      if (mat.map) mat.map.anisotropy = maxAniso;
      // Das Luftbild enthaelt schon echtes Licht und Schatten: Sonnenlicht nur abgeschwaecht wirken lassen
      mat.roughness = 1;
      // beidseitig, damit die senkrechten "Schuerzen" zwischen den Detailstufen von allen Seiten Spalten abdecken
      mat.side = THREE.DoubleSide;
      mat.envMapIntensity = 0.6;
    }
  });
  return gltf.scene;
}
