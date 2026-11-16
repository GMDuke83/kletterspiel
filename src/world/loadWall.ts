import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

export interface Grip {
  name: string;
  type: string;
  node: THREE.Object3D;
}

export interface WallAsset {
  root: THREE.Object3D;
  colliders: THREE.Mesh[];
  grips: Grip[];
  triangles: number;
}

const GRIP_COLORS: Record<string, number> = { jug: 0xff5a1f };

function triCount(geo: THREE.BufferGeometry): number {
  return (geo.index ? geo.index.count : geo.attributes.position.count) / 3;
}

/**
 * Laedt eine Wand-/Fels-GLB aus Blender.
 * Konventionen: Meshes mit Praefix "col_" sind Kollision (unsichtbar),
 * Empties mit Praefix "grip_" sind Griffpunkte (lokale Z-Achse = Flaechennormale).
 */
export async function loadWall(url: string): Promise<WallAsset> {
  const gltf = await new GLTFLoader().loadAsync(url);
  const colliders: THREE.Mesh[] = [];
  const grips: Grip[] = [];
  let triangles = 0;

  gltf.scene.traverse((o) => {
    if (o instanceof THREE.Mesh) {
      if (o.name.startsWith('col_') || o.userData.collider) {
        o.visible = false;
        o.material = new THREE.MeshBasicMaterial({ color: 0x00ff88, wireframe: true });
        colliders.push(o);
      } else {
        o.castShadow = true;
        o.receiveShadow = true;
        triangles += triCount(o.geometry);
      }
    } else if (o.name.startsWith('grip_')) {
      const type = (o.userData.grip_type as string | undefined) ?? 'jug';
      grips.push({ name: o.name, type, node: o });
    }
  });

  // Griff-Marker: kleine Kugel + Pfeil entlang der Flaechennormale
  for (const g of grips) {
    const color = GRIP_COLORS[g.type] ?? 0xffff00;
    const marker = new THREE.Mesh(
      new THREE.SphereGeometry(0.045, 16, 12),
      new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.4 }),
    );
    g.node.add(marker);
    g.node.add(new THREE.ArrowHelper(new THREE.Vector3(0, 0, 1), new THREE.Vector3(), 0.18, color));
  }

  return { root: gltf.scene, colliders, grips, triangles };
}
