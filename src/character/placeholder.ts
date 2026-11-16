import * as THREE from 'three';
import type { Climber, Side } from '../climbing/climber';

export const HAND_COLORS: Record<Side, number> = { left: 0xff7a3d, right: 0x3dc6ff };

const UP = new THREE.Vector3(0, 1, 0);
const Y = new THREE.Vector3(0, 1, 0);

/** Einfache Platzhalter-Figur: Kapsel-Koerper, Kopf, Arme/Beine als Zylinder, Haende als Kugeln. */
export class PlaceholderFigure {
  readonly group = new THREE.Group();
  private torso: THREE.Mesh;
  private head: THREE.Mesh;
  private arms: Record<Side, THREE.Mesh>;
  private legs: THREE.Mesh[];
  private hands: Record<Side, THREE.Mesh>;
  private tmp = new THREE.Vector3();

  constructor() {
    const skin = new THREE.MeshStandardMaterial({ color: 0xd9a77c, roughness: 0.7 });
    const shirt = new THREE.MeshStandardMaterial({ color: 0xc8402f, roughness: 0.8 });
    const pants = new THREE.MeshStandardMaterial({ color: 0x2e3b4e, roughness: 0.9 });
    const limb = new THREE.CylinderGeometry(0.045, 0.04, 1, 8);
    limb.translate(0, 0.5, 0); // Ursprung am Anfang des Glieds

    this.torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.17, 0.42, 6, 12), shirt);
    this.head = new THREE.Mesh(new THREE.SphereGeometry(0.12, 16, 12), skin);
    this.arms = { left: new THREE.Mesh(limb, shirt), right: new THREE.Mesh(limb, shirt) };
    this.legs = [new THREE.Mesh(limb, pants), new THREE.Mesh(limb, pants)];
    this.legs.forEach((l) => l.scale.set(1.5, 1, 1.5));
    const handGeo = new THREE.SphereGeometry(0.065, 16, 12);
    this.hands = {
      left: new THREE.Mesh(handGeo, new THREE.MeshStandardMaterial({ color: HAND_COLORS.left, emissive: HAND_COLORS.left, emissiveIntensity: 0.25 })),
      right: new THREE.Mesh(handGeo, new THREE.MeshStandardMaterial({ color: HAND_COLORS.right, emissive: HAND_COLORS.right, emissiveIntensity: 0.25 })),
    };
    for (const m of [this.torso, this.head, ...Object.values(this.arms), ...this.legs, ...Object.values(this.hands)]) {
      m.castShadow = true;
      this.group.add(m);
    }
  }

  private setLimb(mesh: THREE.Mesh, a: THREE.Vector3, b: THREE.Vector3): void {
    const dir = this.tmp.subVectors(b, a);
    const len = dir.length();
    mesh.position.copy(a);
    mesh.scale.y = Math.max(0.01, len);
    mesh.quaternion.setFromUnitVectors(Y, dir.divideScalar(len || 1));
  }

  update(c: Climber, time: number): void {
    const b = c.body;
    this.torso.position.copy(b);
    // Koerper leicht zur Wand geneigt
    this.torso.quaternion.setFromAxisAngle(c.right, -0.12);
    this.head.position.copy(b).addScaledVector(UP, 0.52).addScaledVector(c.out, 0.03);

    for (const side of ['left', 'right'] as const) {
      const hand = c.hands[side];
      this.hands[side].position.copy(hand.pos);
      this.setLimb(this.arms[side], c.shoulder(side), hand.pos);
    }

    // Beine baumeln unter der Huefte, leicht zur Wand
    const swing = c.state === 'falling' ? 0.4 : Math.sin(time * 1.3) * 0.04;
    this.legs.forEach((leg, i) => {
      const s = i === 0 ? -1 : 1;
      const hip = new THREE.Vector3().copy(b).addScaledVector(UP, -0.3).addScaledVector(c.right, 0.1 * s);
      const foot = hip
        .clone()
        .addScaledVector(UP, -0.82)
        .addScaledVector(c.out, -0.12 + swing * s)
        .addScaledVector(c.right, 0.06 * s);
      this.setLimb(leg, hip, foot);
    });
  }
}
