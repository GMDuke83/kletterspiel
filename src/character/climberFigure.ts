import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import type { Climber, Side } from '../climbing/climber';
import type { WallProbe } from '../climbing/climber';

const UP = new THREE.Vector3(0, 1, 0);
const ANCHOR_H = 1.05; // Hoehe des Modell-Punkts, der auf climber.body liegt (Huefte/Bauch)
const LEAN = THREE.MathUtils.degToRad(9); // Oberkoerper leicht zur Wand geneigt

interface FootState {
  planted: THREE.Vector3 | null;
  from: THREE.Vector3;
  to: THREE.Vector3;
  t: number; // 1 = steht
}

/**
 * Eigene Kletterfigur (scripts/blender/make_climber.py) mit prozeduraler Bewegung:
 * Zwei-Knochen-IK fuer Arme (Hand exakt am Griff) und Beine (Fuesse auf dem Fels, setzen nach),
 * Oberkoerper zwischen Haenden und Fuessen, Kopf schaut zum Ziel, Zittern bei wenig Ausdauer.
 * Die Spielmechanik (Climber) bleibt unveraendert; die Figur folgt ihr nur optisch.
 */
export class ClimberFigure {
  readonly root: THREE.Object3D;
  private bones = new Map<string, THREE.Bone>();
  private rest = new Map<THREE.Bone, THREE.Quaternion>();
  private restDir = new Map<THREE.Bone, THREE.Vector3>();
  private len = { upper: 0.3, fore: 0.26, hand: 0.095, thigh: 0.42, shin: 0.42 };
  private feet: Record<Side, FootState> = {
    left: { planted: null, from: new THREE.Vector3(), to: new THREE.Vector3(), t: 1 },
    right: { planted: null, from: new THREE.Vector3(), to: new THREE.Vector3(), t: 1 },
  };
  private torso = new THREE.Vector3();

  private constructor(root: THREE.Object3D) {
    this.root = root;
    root.traverse((o) => {
      // GLTFLoader entfernt Punkte aus Namen ("upper_arm.L" -> "upper_armL"); bone() loest beides auf
      if (o instanceof THREE.Bone) this.bones.set(o.name, o);
      if (o instanceof THREE.Mesh) {
        o.castShadow = true;
        o.frustumCulled = false;
      }
    });
    for (const b of this.bones.values()) {
      this.rest.set(b, b.quaternion.clone());
      const child = b.children.find((c) => c instanceof THREE.Bone);
      this.restDir.set(b, child ? child.position.clone().normalize() : new THREE.Vector3(0, 1, 0));
    }
    // Laenge eines Knochens = Abstand zum Kind-Gelenk
    const d = (child: string) => this.bone(child)?.position.length() ?? 0;
    this.len.upper = d('forearm.L') || 0.3;
    this.len.fore = d('hand.L') || 0.26;
    this.len.thigh = d('shin.L') || 0.42;
    this.len.shin = d('foot.L') || 0.42;
  }

  static async load(url: string): Promise<ClimberFigure> {
    const gltf = await new GLTFLoader().loadAsync(url);
    return new ClimberFigure(gltf.scene);
  }

  private bone(name: string): THREE.Bone | undefined {
    return this.bones.get(name) ?? this.bones.get(name.replace('.', '_')) ?? this.bones.get(name.replace('.', ''));
  }

  /** Knochen so drehen, dass er (minimal) auf einen Weltpunkt zeigt. */
  private aim(b: THREE.Bone | undefined, target: THREE.Vector3, maxAngle = Math.PI): void {
    if (!b) return;
    b.updateWorldMatrix(true, false);
    const pos = new THREE.Vector3().setFromMatrixPosition(b.matrixWorld);
    const wq = b.getWorldQuaternion(new THREE.Quaternion());
    const cur = this.restDir.get(b)!.clone().applyQuaternion(wq);
    const want = target.clone().sub(pos);
    if (want.lengthSq() < 1e-8) return;
    want.normalize();
    const swing = new THREE.Quaternion().setFromUnitVectors(cur, want);
    if (maxAngle < Math.PI) {
      const ang = 2 * Math.acos(Math.min(1, Math.abs(swing.w)));
      if (ang > maxAngle) swing.slerp(new THREE.Quaternion(), 1 - maxAngle / ang);
    }
    const newWorld = swing.multiply(wq);
    const parentWq = (b.parent as THREE.Object3D).getWorldQuaternion(new THREE.Quaternion());
    b.quaternion.copy(parentWq.invert().multiply(newWorld));
    b.updateWorldMatrix(false, true);
  }

  private worldPos(name: string): THREE.Vector3 {
    const b = this.bone(name);
    if (!b) return new THREE.Vector3();
    b.updateWorldMatrix(true, false);
    return new THREE.Vector3().setFromMatrixPosition(b.matrixWorld);
  }

  /** Zwei-Knochen-IK: Lage des Mittelgelenks. */
  private solve(a: THREE.Vector3, t: THREE.Vector3, l1: number, l2: number, pole: THREE.Vector3): THREE.Vector3 {
    const dirV = t.clone().sub(a);
    const dist = THREE.MathUtils.clamp(dirV.length(), 1e-4, (l1 + l2) * 0.999);
    const dir = dirV.normalize();
    const cosA = THREE.MathUtils.clamp((l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist), -1, 1);
    const sinA = Math.sqrt(1 - cosA * cosA);
    const perp = pole.clone().addScaledVector(dir, -pole.dot(dir));
    if (perp.lengthSq() < 1e-6) perp.set(0, -1, 0).addScaledVector(dir, dir.y);
    perp.normalize();
    return a.clone().addScaledVector(dir, l1 * cosA).addScaledVector(perp, l1 * sinA);
  }

  update(c: Climber, time: number, dt: number, probe: WallProbe, groundY: number, look: THREE.Vector3 | null): void {
    for (const [b, q] of this.rest) b.quaternion.copy(q);

    const out = c.out;
    const right = c.right;
    const falling = c.state === 'falling';

    // Ausrichtung: Gesicht zur Wand (-out), Oberkoerper leicht zur Wand geneigt
    const yaw = Math.atan2(-out.x, -out.z);
    const qYaw = new THREE.Quaternion().setFromAxisAngle(UP, yaw);
    const qLean = new THREE.Quaternion().setFromAxisAngle(right, -LEAN);
    this.root.quaternion.copy(qLean.multiply(qYaw));

    // Zittern bei wenig Ausdauer
    const held = (['left', 'right'] as Side[]).filter((s) => c.holding(c.hands[s]));
    const minSt = held.length ? Math.min(...held.map((s) => c.hands[s].stamina)) : 1;
    const shake = Math.max(0, 0.45 - minSt) * 0.03;
    this.torso.copy(c.body);
    this.torso.x += Math.sin(time * 37) * shake;
    this.torso.y += Math.sin(time * 29 + 1) * shake * 0.6 + Math.sin(time * 1.6) * 0.006; // Atmen

    // Oberkoerper so weit zu den Haenden ziehen, dass die Arme sie erreichen
    const armLen = (this.len.upper + this.len.fore + this.len.hand) * 0.97;
    for (let it = 0; it < 4 && !falling; it++) {
      const shift = new THREE.Vector3();
      let n = 0;
      for (const s of ['left', 'right'] as Side[]) {
        const h = c.hands[s];
        if (!h.grip && !h.target) continue;
        const sh = this.torso.clone().addScaledVector(UP, 0.37).addScaledVector(right, s === 'left' ? -0.19 : 0.19);
        const d = h.pos.clone().sub(sh);
        const ex = d.length() - armLen;
        if (ex > 0) {
          shift.addScaledVector(d.normalize(), ex);
          n++;
        }
      }
      if (!n) break;
      this.torso.addScaledVector(shift, 1 / n);
    }
    // nicht in den Fels
    const dWall = probe(this.torso, out);
    if (dWall !== null && dWall < 0.2) this.torso.addScaledVector(out, 0.2 - dWall);

    const anchor = new THREE.Vector3(0, ANCHOR_H, 0).applyQuaternion(this.root.quaternion);
    this.root.position.copy(this.torso).sub(anchor);
    this.root.updateMatrixWorld(true);

    // ------------------------------------------------ Arme
    for (const s of ['left', 'right'] as Side[]) {
      const k = s === 'left' ? 'L' : 'R';
      const sideV = right.clone().multiplyScalar(s === 'left' ? -1 : 1);
      const shoulder = this.worldPos(`upper_arm.${k}`);
      let target: THREE.Vector3;
      if (falling) {
        target = shoulder.clone().addScaledVector(UP, 0.45).addScaledVector(sideV, 0.25).addScaledVector(out, 0.15);
      } else {
        target = c.hands[s].pos.clone().addScaledVector(out, 0.02);
      }
      const dir = target.clone().sub(shoulder).normalize();
      const wrist = target.clone().addScaledVector(dir, -this.len.hand);
      const pole = new THREE.Vector3().addScaledVector(UP, -0.9).addScaledVector(sideV, 0.55).addScaledVector(out, -0.1);
      const elbow = this.solve(shoulder, wrist, this.len.upper, this.len.fore, pole);
      this.aim(this.bone(`upper_arm.${k}`), elbow);
      this.aim(this.bone(`forearm.${k}`), wrist);
      this.aim(this.bone(`hand.${k}`), target);
    }

    // ------------------------------------------------ Beine
    const legLen = this.len.thigh + this.len.shin;
    for (const s of ['left', 'right'] as Side[]) {
      const k = s === 'left' ? 'L' : 'R';
      const sideV = right.clone().multiplyScalar(s === 'left' ? -1 : 1);
      const hip = this.worldPos(`thigh.${k}`);
      const f = this.feet[s];
      let foot: THREE.Vector3;
      if (falling) {
        f.planted = null;
        foot = hip.clone().addScaledVector(UP, -legLen * 0.9).addScaledVector(out, 0.15).addScaledVector(sideV, 0.08);
      } else {
        // Wunschposition: unter der Huefte, leicht nach aussen, auf dem Fels
        const ideal = hip.clone().addScaledVector(UP, -legLen * 0.8).addScaledVector(sideV, 0.1);
        const d = probe(ideal, out);
        if (d !== null) ideal.addScaledVector(out, 0.07 - d);
        ideal.y = Math.max(ideal.y, groundY + 0.06);
        if (!f.planted) {
          f.planted = ideal.clone();
          f.t = 1;
        }
        const other = this.feet[s === 'left' ? 'right' : 'left'];
        const tooFar = f.planted.distanceTo(ideal) > 0.33 || f.planted.distanceTo(hip) > legLen * 0.98;
        if (f.t >= 1 && tooFar && other.t >= 1) {
          f.from.copy(f.planted);
          f.to.copy(ideal);
          f.t = 0;
        }
        if (f.t < 1) {
          f.t = Math.min(1, f.t + dt / 0.22);
          f.to.lerp(ideal, 0.2);
          f.planted.lerpVectors(f.from, f.to, f.t * f.t * (3 - 2 * f.t)).addScaledVector(out, Math.sin(Math.PI * f.t) * 0.08);
        }
        foot = f.planted;
      }
      const pole = new THREE.Vector3().addScaledVector(out, -0.5).addScaledVector(sideV, 0.8).addScaledVector(UP, 0.2);
      const knee = this.solve(hip, foot, this.len.thigh, this.len.shin, pole);
      this.aim(this.bone(`thigh.${k}`), knee);
      this.aim(this.bone(`shin.${k}`), foot);
      // Fussspitze zur Wand
      this.aim(this.bone(`foot.${k}`), foot.clone().addScaledVector(out, -0.2).addScaledVector(UP, -0.05));
    }

    // ------------------------------------------------ Kopf
    const head = this.bone('head');
    if (head) {
      const hp = this.worldPos('head');
      const tgt = look ?? hp.clone().addScaledVector(UP, 1).addScaledVector(out, -0.4);
      // Kopf "zeigt" nach oben (Knochenrichtung); fuer den Blick nur begrenzt in Richtung Ziel neigen
      const dirUp = tgt.clone().sub(hp).normalize().add(UP.clone().multiplyScalar(1.4)).normalize();
      this.aim(head, hp.clone().add(dirUp), THREE.MathUtils.degToRad(35));
    }
  }
}
