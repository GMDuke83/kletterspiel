import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import type { Grip, GripType } from '../climbing/grip';

export interface WallAsset {
  root: THREE.Object3D;
  /** sichtbare Meshes (fuer Raycasts gegen die Wand) */
  surfaces: THREE.Mesh[];
  colliders: THREE.Mesh[];
  grips: Grip[];
  triangles: number;
}

function triCount(geo: THREE.BufferGeometry): number {
  return (geo.index ? geo.index.count : geo.attributes.position.count) / 3;
}

const loader = new GLTFLoader();

/**
 * Laedt eine Wand-/Fels-GLB aus Blender.
 * Konventionen: Meshes mit Praefix "col_" sind Kollision (unsichtbar),
 * Empties mit Praefix "grip_" sind Griffpunkte. Die lokale Blender-Z-Achse
 * (= Flaechennormale) ist nach dem glTF-Export die lokale +Y-Achse.
 */
export async function loadWall(url: string): Promise<WallAsset> {
  const gltf = await loader.loadAsync(url);
  const root = gltf.scene;
  root.updateMatrixWorld(true);

  const surfaces: THREE.Mesh[] = [];
  const colliders: THREE.Mesh[] = [];
  const grips: Grip[] = [];
  let triangles = 0;

  root.traverse((o) => {
    if (o instanceof THREE.Mesh) {
      if (o.name.startsWith('col_') || o.userData.collider) {
        o.visible = false;
        o.material = new THREE.MeshBasicMaterial({ color: 0x00ff88, wireframe: true });
        colliders.push(o);
      } else {
        o.castShadow = true;
        o.receiveShadow = true;
        surfaces.push(o);
        triangles += triCount(o.geometry);
        const mat = o.material as THREE.MeshStandardMaterial;
        if (mat.normalMap) mat.normalScale.set(1.6, 1.6); // Felsstruktur etwas kraeftiger
      }
    } else if (o.name.startsWith('grip_')) {
      const ud = o.userData as { grip_type?: string; start?: number; summit?: number };
      const position = new THREE.Vector3();
      o.getWorldPosition(position);
      const q = new THREE.Quaternion();
      o.getWorldQuaternion(q);
      const normal = new THREE.Vector3(0, 1, 0).applyQuaternion(q).normalize();
      grips.push({
        id: grips.length,
        name: o.name,
        type: (ud.grip_type as GripType | undefined) ?? 'jug',
        start: !!ud.start,
        summit: !!ud.summit,
        position,
        normal,
        node: o,
      });
    }
  });

  return { root, surfaces, colliders, grips, triangles };
}
