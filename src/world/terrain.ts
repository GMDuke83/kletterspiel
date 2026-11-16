import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { applyTerrainDetail, type TerrainDetailOptions } from '../render/terrainMaterial';

/**
 * Laedt ein Gelaende-GLB (aus scripts/terrain/build_terrain.py bzw. build_near.py).
 * Koordinaten: x = Osten, y = Hoehe ueber Meer, z = Sueden (Meter, 1:1).
 * detail = null -> einfache Darstellung (Qualitaet "niedrig").
 */
export async function loadTerrain(
  url: string,
  renderer: THREE.WebGLRenderer,
  detail: TerrainDetailOptions | null,
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
      mat.roughness = 1;
      mat.envMapIntensity = 0.6;
      // beidseitig, damit die senkrechten "Schuerzen" zwischen den Detailstufen von allen Seiten Spalten abdecken
      mat.side = THREE.DoubleSide;
      if (detail) applyTerrainDetail(mat, detail);
    }
  });
  return gltf.scene;
}

/**
 * Schnelle Hoehenabfrage aus einem regelmaessigen Gelaende-Gitter (build_near.py):
 * die ersten (n+1)^2 Punkte sind das Gitter, Zeile 0 = Norden (kleinstes z), Spalte = Osten.
 * Liefert -Infinity ausserhalb des Gitters.
 */
export function makeHeightSampler(
  root: THREE.Object3D,
  minX: number,
  minZ: number,
  step: number,
  size: number,
): (x: number, z: number) => number {
  let pos: THREE.BufferAttribute | null = null;
  root.traverse((o) => {
    if (!pos && o instanceof THREE.Mesh) pos = o.geometry.getAttribute('position') as THREE.BufferAttribute;
  });
  const n = Math.round(size / step);
  return (x, z) => {
    if (!pos) return -Infinity;
    const c = (x - minX) / step;
    const r = (z - minZ) / step;
    if (c < 0 || r < 0 || c >= n || r >= n) return -Infinity;
    const c0 = Math.floor(c);
    const r0 = Math.floor(r);
    const fc = c - c0;
    const fr = r - r0;
    const h = (rr: number, cc: number) => pos!.getY(rr * (n + 1) + cc);
    return (h(r0, c0) * (1 - fc) + h(r0, c0 + 1) * fc) * (1 - fr) + (h(r0 + 1, c0) * (1 - fc) + h(r0 + 1, c0 + 1) * fc) * fr;
  };
}
