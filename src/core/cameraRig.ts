import * as THREE from 'three';

/** Third-Person-Kamera hinter der Figur (von der Wand weg), Mausrad = Abstand. */
export class CameraRig {
  distance = 4.2;
  private pos = new THREE.Vector3();
  private look = new THREE.Vector3();
  private initialized = false;

  constructor(
    readonly camera: THREE.PerspectiveCamera,
    dom: HTMLElement,
  ) {
    dom.addEventListener(
      'wheel',
      (e) => {
        e.preventDefault();
        this.distance = THREE.MathUtils.clamp(this.distance * (e.deltaY > 0 ? 1.1 : 0.9), 2.2, 12);
      },
      { passive: false },
    );
  }

  update(target: THREE.Vector3, out: THREE.Vector3, dt: number): void {
    const wantPos = new THREE.Vector3()
      .copy(target)
      .addScaledVector(out, this.distance)
      .add(new THREE.Vector3(0, 0.9 + this.distance * 0.08, 0));
    const wantLook = new THREE.Vector3().copy(target).add(new THREE.Vector3(0, 0.6, 0));
    const k = this.initialized ? 1 - Math.exp(-dt * 4) : 1;
    this.pos.lerp(wantPos, k);
    this.look.lerp(wantLook, k);
    this.initialized = true;
    this.camera.position.copy(this.pos);
    this.camera.lookAt(this.look);
  }
}
