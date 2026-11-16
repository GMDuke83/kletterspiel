import * as THREE from 'three';

/**
 * Third-Person-Kamera hinter der Figur (von der Wand weg).
 * Mausrad = Abstand. Drehen: mittlere Maustaste ziehen, Pfeiltasten oder A/D/W/S
 * (seitlich bis ca. 85 Grad, damit die Kamera nicht hinter die Wand faehrt).
 * V = Aussicht: Kamera am Kopf der Figur, Blick von der Wand weg ins Tal (frei drehbar).
 * Leertaste = Kamera zuruecksetzen.
 */
export class CameraRig {
  distance = 4.2;
  /** Drehung um die Figur (rad), 0 = direkt hinter der Figur */
  yaw = 0;
  /** Startwert fuer yaw (Leertaste setzt hierauf zurueck) */
  defaultYaw = 0;
  /** Neigung (rad), positiv = von oben */
  pitch = 0.18;
  /** Aussichts-Modus (Taste V): Blick von der Wand weg */
  lookout = false;
  /** optionale Gelaendehoehe: die Kamera bleibt darueber (faehrt nicht in den Berg) */
  ground: ((x: number, z: number) => number) | null = null;
  private lookYaw = 0;
  private lookPitch = -0.15;
  private pos = new THREE.Vector3();
  private look = new THREE.Vector3();
  private initialized = false;
  private keys = new Set<string>();
  private dragging = false;

  constructor(
    readonly camera: THREE.PerspectiveCamera,
    dom: HTMLElement,
  ) {
    dom.addEventListener(
      'wheel',
      (e) => {
        e.preventDefault();
        this.distance = THREE.MathUtils.clamp(this.distance * (e.deltaY > 0 ? 1.1 : 0.9), 2.2, 40);
      },
      { passive: false },
    );
    dom.addEventListener('pointerdown', (e) => {
      if (e.button === 1) {
        this.dragging = true;
        e.preventDefault();
      }
    });
    window.addEventListener('pointerup', (e) => {
      if (e.button === 1) this.dragging = false;
    });
    window.addEventListener('pointermove', (e) => {
      if (!this.dragging) return;
      this.turn(-e.movementX * 0.005, e.movementY * 0.004);
    });
    window.addEventListener('keydown', (e) => {
      this.keys.add(e.key.toLowerCase());
      if (e.key === ' ') {
        this.yaw = this.defaultYaw;
        this.pitch = 0.18;
        this.distance = 4.2;
        this.lookout = false;
      }
      if (e.key.toLowerCase() === 'v') {
        this.lookout = !this.lookout;
        this.lookYaw = 0;
        this.lookPitch = -0.15;
      }
    });
    window.addEventListener('keyup', (e) => this.keys.delete(e.key.toLowerCase()));
  }

  update(target: THREE.Vector3, out: THREE.Vector3, dt: number): void {
    const k = this.keys;
    const turn = 1.4 * dt;
    if (k.has('arrowleft') || k.has('a')) this.turn(turn, 0);
    if (k.has('arrowright') || k.has('d')) this.turn(-turn, 0);
    if (k.has('arrowup') || k.has('w')) this.turn(0, turn * 0.7);
    if (k.has('arrowdown') || k.has('s')) this.turn(0, -turn * 0.7);

    if (this.lookout) {
      // Kamera knapp vor dem Kopf, Blick von der Wand weg
      const UPV = new THREE.Vector3(0, 1, 0);
      const eye = target.clone().addScaledVector(UPV, 0.55).addScaledVector(out, 0.45);
      const dir = out.clone().applyAxisAngle(UPV, this.lookYaw);
      const right = new THREE.Vector3().crossVectors(dir, UPV).normalize();
      dir.applyAxisAngle(right, this.lookPitch);
      const f = this.initialized ? 1 - Math.exp(-dt * 8) : 1;
      this.pos.lerp(eye, f);
      this.look.lerp(eye.clone().add(dir.multiplyScalar(100)), f);
      this.camera.position.copy(this.pos);
      this.camera.lookAt(this.look);
      this.initialized = true;
      return;
    }

    const dir = out.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), this.yaw);
    const horiz = Math.cos(this.pitch) * this.distance;
    const wantPos = new THREE.Vector3()
      .copy(target)
      .addScaledVector(dir, horiz)
      .add(new THREE.Vector3(0, 0.9 + Math.sin(this.pitch) * this.distance, 0));
    const wantLook = new THREE.Vector3().copy(target).add(new THREE.Vector3(0, 0.6, 0));
    if (this.ground) {
      // vom Blickpunkt zur Kamera laufen; liegt ein Punkt im Fels, Kamera davor stoppen
      const seg = wantPos.clone().sub(wantLook);
      const p = new THREE.Vector3();
      let keep = 1;
      for (let i = 2; i <= 16; i++) {
        const t = i / 16;
        p.copy(wantLook).addScaledVector(seg, t);
        if (p.y < this.ground(p.x, p.z) + 0.6) {
          keep = Math.max(1.4 / seg.length(), (i - 1) / 16);
          break;
        }
      }
      wantPos.copy(wantLook).addScaledVector(seg, keep);
    }
    const f = this.initialized ? 1 - Math.exp(-dt * 5) : 1;
    this.pos.lerp(wantPos, f);
    this.look.lerp(wantLook, f);
    this.initialized = true;
    this.camera.position.copy(this.pos);
    this.camera.lookAt(this.look);
  }

  private turn(dYaw: number, dPitch: number): void {
    if (this.lookout) {
      this.lookYaw = THREE.MathUtils.clamp(this.lookYaw + dYaw, -2.2, 2.2);
      this.lookPitch = THREE.MathUtils.clamp(this.lookPitch + dPitch, -1.2, 0.9);
    } else {
      this.yaw = THREE.MathUtils.clamp(this.yaw + dYaw, -1.48, 1.48);
      this.pitch = THREE.MathUtils.clamp(this.pitch + dPitch, -0.6, 1.3);
    }
  }
}
