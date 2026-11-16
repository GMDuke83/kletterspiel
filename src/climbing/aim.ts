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
  private markers = new THREE.Group();
  private hoverDot: THREE.Mesh;

  constructor(
    private readonly grips: Grip[],
    scene: THREE.Scene,
    dom: HTMLElement,
  ) {
    dom.addEventListener('pointermove', (e) => this.mouse.set(e.clientX, e.clientY));
    dom.addEventListener('pointerleave', () => this.mouse.set(-9999, -9999));

    this.ringMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9 });
    this.ring = new THREE.Mesh(new THREE.TorusGeometry(0.11, 0.014, 8, 32), this.ringMat);
    this.ring.renderOrder = 10;
    this.ring.visible = false;
    scene.add(this.ring);

    // dezente farbige Punkte je Grifftyp (abschaltbar ueber "Griffe anzeigen")
    const geo = new THREE.SphereGeometry(0.016, 10, 8);
    for (const g of grips) {
      const color = g.summit ? 0xff3b30 : GRIP_INFO[g.type].color;
      const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.85 }));
      m.position.copy(g.position).addScaledVector(g.normal, 0.015);
      this.markers.add(m);
    }
    scene.add(this.markers);
    this.hoverDot = new THREE.Mesh(
      new THREE.SphereGeometry(0.022, 12, 8),
      new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false }),
    );
    this.hoverDot.renderOrder = 11;
    this.hoverDot.visible = false;
    scene.add(this.hoverDot);
  }

  /** Farbpunkte an allen Griffen ein-/ausblenden (beim Anvisieren wird der Typ immer gezeigt) */
  set showMarkers(v: boolean) {
    this.markers.visible = v;
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
      this.ring.quaternion.copy(camera.quaternion); // Ring immer zur Kamera gedreht
      // feste Bildschirmgroesse (~28 px Durchmesser), leicht zur Kamera hin versetzt
      const cam = camera as THREE.PerspectiveCamera;
      const dist = cam.position.distanceTo(this.ring.position);
      const worldPerPx = (2 * dist * Math.tan(THREE.MathUtils.degToRad(cam.fov / 2))) / height;
      this.ring.scale.setScalar((14 * worldPerPx) / 0.11);
      this.ring.position.addScaledVector(this.v.copy(cam.position).sub(this.ring.position).normalize(), 0.06);
      this.ringMat.color.setHex(reachable(best) ? 0x4cd964 : 0xff453a);
      this.hoverDot.position.copy(best.position).addScaledVector(best.normal, 0.03);
      (this.hoverDot.material as THREE.MeshBasicMaterial).color.setHex(
        best.summit ? 0xff3b30 : GRIP_INFO[best.type].color,
      );
    }
    this.hoverDot.visible = !!best;
  }
}
