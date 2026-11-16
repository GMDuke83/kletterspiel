import * as THREE from 'three';
import { GRIP_INFO, type Grip } from './grip';

const PICK_RADIUS_PX = 70;

/** Waehlt den Griff, der dem Mauszeiger auf dem Bildschirm am naechsten liegt. */
export class GripAim {
  hovered: Grip | null = null;
  private mouse = new THREE.Vector2(-9999, -9999);
  private ring: THREE.Mesh;
  private ringMat: THREE.MeshBasicMaterial;
  private v = new THREE.Vector3();

  constructor(
    private readonly grips: Grip[],
    scene: THREE.Scene,
    dom: HTMLElement,
  ) {
    dom.addEventListener('pointermove', (e) => this.mouse.set(e.clientX, e.clientY));
    dom.addEventListener('pointerleave', () => this.mouse.set(-9999, -9999));

    this.ringMat = new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false, transparent: true });
    this.ring = new THREE.Mesh(new THREE.TorusGeometry(0.11, 0.014, 8, 32), this.ringMat);
    this.ring.renderOrder = 10;
    this.ring.visible = false;
    scene.add(this.ring);

    // kleine farbige Marker je Grifftyp
    const geo = new THREE.SphereGeometry(0.025, 10, 8);
    for (const g of grips) {
      const color = g.summit ? 0xff3b30 : GRIP_INFO[g.type].color;
      const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color }));
      m.position.copy(g.position).addScaledVector(g.normal, 0.02);
      scene.add(m);
    }
  }

  update(camera: THREE.Camera, width: number, height: number, reachable: (g: Grip) => boolean): void {
    let best: Grip | null = null;
    let bestD = PICK_RADIUS_PX;
    for (const g of this.grips) {
      this.v.copy(g.position).project(camera);
      if (this.v.z > 1) continue;
      const sx = (this.v.x * 0.5 + 0.5) * width;
      const sy = (-this.v.y * 0.5 + 0.5) * height;
      const d = Math.hypot(sx - this.mouse.x, sy - this.mouse.y);
      if (d < bestD) {
        bestD = d;
        best = g;
      }
    }
    this.hovered = best;
    this.ring.visible = !!best;
    if (best) {
      this.ring.position.copy(best.position).addScaledVector(best.normal, 0.03);
      this.ring.lookAt(this.v.copy(best.position).add(best.normal));
      this.ringMat.color.setHex(reachable(best) ? 0x4cd964 : 0xff453a);
    }
  }
}
