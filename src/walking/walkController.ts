import * as THREE from 'three';
import type { Walker, WalkInput } from './walker';

/**
 * Ego-Shooter-Steuerung fuer den Gehmodus:
 * WASD bewegen, Maus schaut (Klick = Maus einfangen, Esc = freigeben), Shift = schneller,
 * Leertaste = kleiner Sprung, C = Schulter-/Ich-Perspektive.
 */
export class WalkController {
  active = false;
  firstPerson = false;
  private keys = new Set<string>();
  private camPos = new THREE.Vector3();
  private init = false;

  constructor(
    private readonly walker: Walker,
    private readonly camera: THREE.PerspectiveCamera,
    private readonly dom: HTMLElement,
    private readonly ground: (x: number, z: number) => number,
  ) {
    window.addEventListener('keydown', (e) => {
      if (!this.active) return;
      const k = e.key.toLowerCase();
      this.keys.add(k);
      if (k === 'c') this.firstPerson = !this.firstPerson;
      if (k === ' ') e.preventDefault();
    });
    window.addEventListener('keyup', (e) => this.keys.delete(e.key.toLowerCase()));
    dom.addEventListener('click', () => {
      if (this.active && document.pointerLockElement !== dom) dom.requestPointerLock?.();
    });
    window.addEventListener('mousemove', (e) => {
      if (!this.active || document.pointerLockElement !== dom) return;
      this.walker.yaw -= e.movementX * 0.0025;
      this.walker.pitch = THREE.MathUtils.clamp(this.walker.pitch - e.movementY * 0.0022, -1.2, 1.1);
    });
  }

  setActive(on: boolean): void {
    this.active = on;
    this.keys.clear();
    this.init = false;
    if (!on && document.pointerLockElement === this.dom) document.exitPointerLock();
  }

  get pointerLocked(): boolean {
    return document.pointerLockElement === this.dom;
  }

  input(): WalkInput {
    const k = this.keys;
    // Pfeiltasten drehen auch ohne Maus
    return {
      forward: (k.has('w') || k.has('arrowup') ? 1 : 0) - (k.has('s') || k.has('arrowdown') ? 1 : 0),
      strafe: (k.has('d') ? 1 : 0) - (k.has('a') ? 1 : 0),
      run: k.has('shift'),
      jump: k.has(' '),
    };
  }

  update(dt: number): void {
    const k = this.keys;
    if (k.has('arrowleft')) this.walker.yaw += 1.8 * dt;
    if (k.has('arrowright')) this.walker.yaw -= 1.8 * dt;

    const w = this.walker;
    const look = new THREE.Vector3(
      -Math.sin(w.yaw) * Math.cos(w.pitch),
      Math.sin(w.pitch),
      -Math.cos(w.yaw) * Math.cos(w.pitch),
    );
    const right = w.rightDir();
    let want: THREE.Vector3;
    let target: THREE.Vector3;
    if (this.firstPerson) {
      want = w.pos.clone().add(new THREE.Vector3(0, 1.66, 0)).addScaledVector(w.forwardDir(), 0.14);
      target = want.clone().addScaledVector(look, 10);
    } else {
      const head = w.pos.clone().add(new THREE.Vector3(0, 1.55, 0));
      want = head.clone().addScaledVector(look, -2.6).addScaledVector(right, 0.45).add(new THREE.Vector3(0, 0.25, 0));
      // Kamera nicht unter den Boden
      const g = this.ground(want.x, want.z);
      if (Number.isFinite(g) && want.y < g + 0.4) want.y = g + 0.4;
      target = head.clone().addScaledVector(look, 6);
    }
    const f = this.init ? 1 - Math.exp(-dt * (this.firstPerson ? 30 : 12)) : 1;
    this.camPos.lerp(want, f);
    this.init = true;
    this.camera.position.copy(this.camPos);
    this.camera.lookAt(target);
  }
}
