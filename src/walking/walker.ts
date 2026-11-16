import * as THREE from 'three';

/** Bodenhoehe an (x, z); -Infinity ausserhalb des bekannten Gelaendes */
export type GroundFn = (x: number, z: number) => number;

export interface WalkInput {
  forward: number; // -1..1 (W/S)
  strafe: number; // -1..1 (D/A)
  run: boolean;
  jump: boolean;
}

export type Terrain = 'normal' | 'steil' | 'kraxeln' | 'zu steil';

const UP = new THREE.Vector3(0, 1, 0);
export const SLOPE_NORMAL = 35;
export const SLOPE_STEEP = 50;
export const SLOPE_MAX = 68; // steiler nur kletternd (Gratkraxelei bis ca. 68 Grad auf dem 1,2-m-Netz)

/**
 * Gehen auf dem echten Gelaende (Ego-Shooter-artig).
 * Hangneigung: bis 35 Grad normal, bis 50 Grad langsam, bis 68 Grad Kraxeln (bis 68 Grad, sehr langsam,
 * kostet Puste, Ausrutschgefahr), darueber nur Klettern. Ueber Kanten faellt man.
 */
export class Walker {
  readonly pos = new THREE.Vector3(); // Fusspunkt
  yaw = 0; // Blickrichtung um die Hochachse (0 = Blick nach -Z)
  pitch = 0;
  readonly vel = new THREE.Vector3();
  airborne = false;
  private fallFrom = 0;
  /** Puste 0..1 (Laufen, Kraxeln) */
  stamina = 1;
  /** zurueckgelegter Weg (fuer die Schrittanimation) */
  travelled = 0;
  speed = 0;
  terrain: Terrain = 'normal';
  /** letzter sicherer Standpunkt (fuer Neustart nach Absturz) */
  readonly safe = new THREE.Vector3();
  message = '';
  messageTime = 0;

  constructor(private readonly ground: GroundFn) {}

  place(p: THREE.Vector3, yaw: number): void {
    this.pos.copy(p);
    const g = this.ground(p.x, p.z);
    if (Number.isFinite(g)) this.pos.y = g;
    this.yaw = yaw;
    this.vel.set(0, 0, 0);
    this.airborne = false;
    this.safe.copy(this.pos);
  }

  forwardDir(out = new THREE.Vector3()): THREE.Vector3 {
    return out.set(-Math.sin(this.yaw), 0, -Math.cos(this.yaw));
  }

  rightDir(out = new THREE.Vector3()): THREE.Vector3 {
    return out.set(Math.cos(this.yaw), 0, -Math.sin(this.yaw));
  }

  slopeAt(x: number, z: number): number {
    const e = 0.6;
    const hx = (this.ground(x + e, z) - this.ground(x - e, z)) / (2 * e);
    const hz = (this.ground(x, z + e) - this.ground(x, z - e)) / (2 * e);
    if (!Number.isFinite(hx) || !Number.isFinite(hz)) return 90;
    return THREE.MathUtils.radToDeg(Math.atan(Math.hypot(hx, hz)));
  }

  private say(m: string): void {
    this.message = m;
    this.messageTime = 2.5;
  }

  /** Gibt die Fallhoehe zurueck, wenn die Figur gerade gelandet ist (sonst 0). */
  update(dt: number, input: WalkInput, altitudeFactor = 1): number {
    if (this.messageTime > 0) this.messageTime -= dt;
    const g = this.ground(this.pos.x, this.pos.z);

    if (this.airborne) {
      this.vel.y -= 9.81 * dt;
      this.pos.addScaledVector(this.vel, dt);
      const gg = this.ground(this.pos.x, this.pos.z);
      if (Number.isFinite(gg) && this.pos.y <= gg) {
        this.pos.y = gg;
        this.airborne = false;
        this.vel.set(0, 0, 0);
        return Math.max(0, this.fallFrom - gg);
      }
      if (!Number.isFinite(gg) && this.pos.y < this.fallFrom - 50) return 999;
      return 0;
    }

    const slopeHere = this.slopeAt(this.pos.x, this.pos.z);
    this.terrain = slopeHere <= SLOPE_NORMAL ? 'normal' : slopeHere <= SLOPE_STEEP ? 'steil' : slopeHere <= SLOPE_MAX ? 'kraxeln' : 'zu steil';

    const dir = this.forwardDir().multiplyScalar(input.forward).addScaledVector(this.rightDir(), input.strafe);
    const moving = dir.lengthSq() > 1e-4;
    let speed = 0;
    if (moving) {
      dir.normalize();
      speed = input.run && this.stamina > 0.05 ? 2.6 : 1.35;
      if (this.terrain === 'steil') speed *= 0.65;
      if (this.terrain === 'kraxeln') speed *= 0.42;
      speed *= altitudeFactor;
      const next = this.pos.clone().addScaledVector(dir, speed * dt);
      const gn = this.ground(next.x, next.z);
      if (!Number.isFinite(gn)) {
        this.say('Hier endet das Gelaende.');
        speed = 0;
      } else {
        const rise = gn - g;
        // Steilheit in Gehrichtung ueber 1,2 m (Netzweite) messen (pro Bild waeren die Schritte zu klein)
        const ahead = this.ground(this.pos.x + dir.x * 1.2, this.pos.z + dir.z * 1.2);
        const ang = THREE.MathUtils.radToDeg(Math.atan2(ahead - g, 1.2));
        if (ang > SLOPE_MAX) {
          this.say('Zu steil zum Gehen - hier musst du klettern.');
          speed = 0;
        } else if (rise < -Math.max(1.2, speed * dt * 4)) {
          // ueber eine Kante getreten
          this.pos.copy(next);
          this.airborne = true;
          this.fallFrom = g;
          this.vel.copy(dir).multiplyScalar(speed);
          this.say('Achtung, Kante!');
          return 0;
        } else {
          this.pos.set(next.x, gn, next.z);
          this.travelled += speed * dt;
        }
      }
    } else if (Number.isFinite(g)) {
      this.pos.y = g;
    }
    this.speed = speed;

    // Puste: Laufen und Kraxeln kosten, Stehen erholt (in der Hoehe langsamer)
    const cost = (input.run && moving ? 0.12 : 0) + (this.terrain === 'kraxeln' && moving ? 0.06 : 0);
    this.stamina = THREE.MathUtils.clamp(this.stamina - cost * dt + (cost ? 0 : 0.08 * altitudeFactor * dt), 0, 1);

    // Kraxeln mit leerer Puste: Ausrutscher
    if (this.terrain === 'kraxeln' && moving && this.stamina < 0.05 && Math.random() < dt * 0.6) {
      this.airborne = true;
      this.fallFrom = this.pos.y;
      this.vel.copy(UP).multiplyScalar(0.5);
      this.say('Ausgerutscht!');
    }

    if (input.jump && !this.airborne && this.stamina > 0.1) {
      this.airborne = true;
      this.fallFrom = this.pos.y;
      this.vel.copy(dir).multiplyScalar(speed).addScaledVector(UP, 2.8);
      this.stamina -= 0.05;
    }

    if (this.terrain !== 'kraxeln' && this.terrain !== 'zu steil') this.safe.copy(this.pos);
    return 0;
  }
}
