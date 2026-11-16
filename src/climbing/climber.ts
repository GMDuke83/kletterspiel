import * as THREE from 'three';
import { GRIP_INFO, overhangAmount, type Grip } from './grip';

export type Side = 'left' | 'right';
export type ClimberState = 'climbing' | 'falling' | 'summit';

export interface Hand {
  side: Side;
  /** Griff, an dem die Hand gerade haelt (null = frei oder unterwegs) */
  grip: Grip | null;
  /** Griff, zu dem die Hand gerade greift */
  target: Grip | null;
  from: THREE.Vector3;
  t: number;
  pos: THREE.Vector3;
  stamina: number;
}

/** Liefert den Abstand von p zur Wand entlang dir (positiv = vor der Wand) oder null. */
export type WallProbe = (p: THREE.Vector3, dir: THREE.Vector3) => number | null;

const UP = new THREE.Vector3(0, 1, 0);
const REACH = 1.12; // Schulter -> Griff (m)
const GRAB_TIME = 0.28; // Sekunden fuer eine Greifbewegung
const BODY_CLEARANCE = 0.24; // Mindestabstand Koerpermitte -> Fels
const GROUND_BODY_Y = 1.0; // Koerpermitte, wenn die Figur am Boden steht
const RESPAWN_DELAY = 1.3;

/** Horizontaler Anteil der Flaechennormale (Richtung "von der Wand weg"). */
function awayFromWall(n: THREE.Vector3, out = new THREE.Vector3()): THREE.Vector3 {
  out.set(n.x, 0, n.z);
  if (out.lengthSq() < 1e-4) out.set(0, 0, 1);
  return out.normalize();
}

export class Climber {
  readonly body = new THREE.Vector3();
  readonly out = new THREE.Vector3(0, 0, 1); // von der Wand weg (horizontal)
  readonly right = new THREE.Vector3(1, 0, 0);
  readonly hands: Record<Side, Hand>;
  state: ClimberState = 'climbing';
  falls = 0;
  elapsed = 0;
  started = false;
  message = '';
  private messageTime = 0;
  private velocity = new THREE.Vector3();
  private fallTimer = 0;
  private lastSafe: [Grip, Grip];
  private readonly startGrips: [Grip, Grip];

  constructor(
    grips: Grip[],
    private readonly probe: WallProbe,
  ) {
    const starts = grips.filter((g) => g.start).sort((a, b) => a.position.x - b.position.x);
    if (starts.length < 2) throw new Error('Wand braucht zwei Start-Griffe (Extra "start")');
    this.startGrips = [starts[0], starts[starts.length - 1]];
    this.lastSafe = this.startGrips;
    const mk = (side: Side): Hand => ({
      side,
      grip: null,
      target: null,
      from: new THREE.Vector3(),
      t: 0,
      pos: new THREE.Vector3(),
      stamina: 1,
    });
    this.hands = { left: mk('left'), right: mk('right') };
    this.reset(true);
  }

  /** Zurueck an den Start (full) oder an den letzten sicheren Punkt. */
  reset(full = false): void {
    const [l, r] = full ? this.startGrips : this.lastSafe;
    if (full) {
      this.lastSafe = this.startGrips;
      this.falls = 0;
      this.elapsed = 0;
      this.started = false;
    }
    for (const [h, g] of [
      [this.hands.left, l],
      [this.hands.right, r],
    ] as const) {
      h.grip = g;
      h.target = null;
      h.pos.copy(g.position);
      h.stamina = 1;
    }
    this.state = 'climbing';
    this.velocity.set(0, 0, 0);
    this.fallTimer = 0;
    this.computeTarget(this.body);
    this.say(full ? 'Los geht’s! Linke/rechte Maustaste greift.' : 'Neuer Versuch vom letzten Rastpunkt.');
  }

  other(side: Side): Hand {
    return side === 'left' ? this.hands.right : this.hands.left;
  }

  holding(h: Hand): boolean {
    return h.grip !== null && h.target === null;
  }

  shoulder(side: Side, out = new THREE.Vector3()): THREE.Vector3 {
    return out
      .copy(this.body)
      .addScaledVector(UP, 0.38)
      .addScaledVector(this.right, side === 'left' ? -0.2 : 0.2);
  }

  canReach(side: Side, g: Grip): boolean {
    return this.shoulder(side).distanceTo(g.position) <= REACH;
  }

  /** Versucht, mit einer Hand einen Griff zu greifen. Gibt eine Meldung zurueck. */
  grab(side: Side, g: Grip): boolean {
    if (this.state !== 'climbing') return false;
    const h = this.hands[side];
    const o = this.other(side);
    const name = side === 'left' ? 'Linke' : 'Rechte';
    if (h.grip === g || h.target === g) return false;
    if (!this.holding(o)) {
      this.say('Erst muss die andere Hand sicher halten.');
      return false;
    }
    if (!this.canReach(side, g)) {
      this.say(`${name} Hand: zu weit weg.`);
      return false;
    }
    h.grip = null;
    h.target = g;
    h.from.copy(h.pos);
    h.t = 0;
    this.started = true;
    return true;
  }

  update(dt: number): void {
    if (this.messageTime > 0) this.messageTime -= dt;
    if (this.state === 'falling') return this.updateFall(dt);
    if (this.state === 'summit') return;
    if (this.started) this.elapsed += dt;

    // Greifbewegungen
    for (const h of [this.hands.left, this.hands.right]) {
      if (!h.target) continue;
      h.t = Math.min(1, h.t + dt / GRAB_TIME);
      const s = h.t * h.t * (3 - 2 * h.t);
      h.pos.lerpVectors(h.from, h.target.position, s).addScaledVector(this.out, Math.sin(Math.PI * h.t) * 0.12);
      if (h.t >= 1) {
        h.grip = h.target;
        h.target = null;
        this.onGrab(h);
      }
    }

    this.updateStamina(dt);
    if (this.state !== 'climbing') return;

    // Koerper zieht sich Richtung Zielposition
    const target = this.computeTarget(new THREE.Vector3());
    this.body.lerp(target, 1 - Math.exp(-dt * 5));
    this.keepOffWall(this.body);

    // freie Haende baumeln
    for (const h of [this.hands.left, this.hands.right]) {
      if (h.grip || h.target) continue;
      const rest = this.shoulder(h.side).addScaledVector(UP, -0.5).addScaledVector(this.out, 0.12);
      h.pos.lerp(rest, 1 - Math.exp(-dt * 8));
    }
  }

  private onGrab(h: Hand): void {
    const g = h.grip!;
    if (g.summit) {
      this.state = 'summit';
      this.say('Gipfel erreicht!');
      return;
    }
    const o = this.other(h.side);
    if (this.holding(o) && g.type === 'jug' && o.grip!.type === 'jug') {
      const [a, b] = h.side === 'left' ? [g, o.grip!] : [o.grip!, g];
      this.lastSafe = [a, b];
    }
  }

  private updateStamina(dt: number): void {
    const L = this.hands.left;
    const R = this.hands.right;
    const bothJugs = this.holding(L) && this.holding(R) && L.grip!.type === 'jug' && R.grip!.type === 'jug';
    for (const h of [L, R]) {
      if (!this.holding(h)) {
        h.stamina = Math.min(1, h.stamina + 0.22 * dt); // ausschuetteln
        continue;
      }
      const g = h.grip!;
      const ov = overhangAmount(g);
      if (bothJugs) {
        h.stamina = Math.min(1, h.stamina + 0.07 * (1 - 0.7 * ov) * dt);
        continue;
      }
      const oneHand = !this.holding(this.other(h.side));
      const rate = GRIP_INFO[g.type].drain * (1 + 2.5 * ov) * (oneHand ? 1.8 : 1);
      h.stamina = Math.max(0, h.stamina - rate * dt);
    }
    for (const h of [L, R]) {
      if (this.holding(h) && h.stamina <= 0) {
        h.grip = null;
        const o = this.other(h.side);
        this.say(`${h.side === 'left' ? 'Linke' : 'Rechte'} Hand rutscht ab!`);
        if (!this.holding(o)) {
          this.fall();
          return;
        }
      }
    }
  }

  private fall(): void {
    this.state = 'falling';
    for (const h of [this.hands.left, this.hands.right]) {
      h.grip = null;
      h.target = null;
    }
    this.velocity.copy(this.out).multiplyScalar(0.8);
    this.fallTimer = 0;
    this.falls++;
    this.say('Absturz!');
  }

  private updateFall(dt: number): void {
    this.velocity.y -= 9.81 * dt;
    const step = this.velocity.clone().multiplyScalar(dt);
    this.body.add(step);
    if (this.body.y <= GROUND_BODY_Y) {
      this.body.y = GROUND_BODY_Y;
      this.velocity.set(0, 0, 0);
    }
    this.keepOffWall(this.body);
    for (const h of [this.hands.left, this.hands.right]) {
      const rest = this.shoulder(h.side).addScaledVector(UP, 0.35);
      h.pos.lerp(rest, 1 - Math.exp(-dt * 10));
    }
    this.fallTimer += dt;
    if (this.fallTimer > RESPAWN_DELAY && this.velocity.y === 0) this.reset(false);
    else if (this.fallTimer > 4) this.reset(false);
  }

  /** Wo der Koerper haengen will, abhaengig von den haltenden Haenden. */
  private computeTarget(out: THREE.Vector3): THREE.Vector3 {
    const held = [this.hands.left, this.hands.right].filter((h) => h.grip);
    if (held.length === 0) return out.copy(this.body);
    const n = new THREE.Vector3();
    const mid = new THREE.Vector3();
    for (const h of held) {
      n.add(h.grip!.normal);
      mid.add(h.grip!.position);
    }
    mid.divideScalar(held.length);
    awayFromWall(n, this.out);
    this.right.crossVectors(UP, this.out).normalize();
    out.copy(mid).addScaledVector(this.out, 0.32);
    if (held.length === 2) {
      // Fuesse stehen auf Tritten: der Koerper wird bis knapp unter die tiefere Hand hochgedrueckt
      const low = Math.min(held[0].grip!.position.y, held[1].grip!.position.y);
      out.y = low - 0.38;
    } else {
      // an einer Hand: tiefer und unter den Arm geschwungen
      const s = held[0].side === 'left' ? 1 : -1;
      out.addScaledVector(UP, -0.75).addScaledVector(this.right, 0.18 * s);
    }
    out.y = Math.max(out.y, GROUND_BODY_Y);
    return out;
  }

  private keepOffWall(p: THREE.Vector3): void {
    const d = this.probe(p, this.out);
    if (d !== null && d < BODY_CLEARANCE) p.addScaledVector(this.out, BODY_CLEARANCE - d);
  }

  say(msg: string): void {
    this.message = msg;
    this.messageTime = 2.5;
  }

  get activeMessage(): string {
    return this.messageTime > 0 || this.state === 'summit' ? this.message : '';
  }

  get height(): number {
    return Math.max(0, this.body.y - GROUND_BODY_Y);
  }
}
