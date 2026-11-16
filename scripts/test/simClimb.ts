/**
 * Node-Test der Klettermechanik ohne Browser:
 *   npx esbuild scripts/test/simClimb.ts --bundle --platform=node --outfile=node_modules/.cache/simClimb.cjs
 *   node node_modules/.cache/simClimb.cjs public/assets/test_wall.glb 300
 * Liest die Griffe direkt aus der GLB (Empties = Kinder der Wand) und laesst den Autopiloten klettern.
 */
import { readFileSync } from 'node:fs';
import * as THREE from 'three';
import { Climber } from '../../src/climbing/climber';
import { Autopilot } from '../../src/climbing/autopilot';
import type { Grip, GripType } from '../../src/climbing/grip';

interface GltfNode {
  name?: string;
  translation?: number[];
  rotation?: number[];
  scale?: number[];
  children?: number[];
  extras?: Record<string, unknown>;
}

const [file, secondsArg] = process.argv.slice(2);
const buf = readFileSync(file);
const jsonLen = buf.readUInt32LE(12);
const gltf = JSON.parse(buf.subarray(20, 20 + jsonLen).toString('utf8')) as { nodes: GltfNode[]; scenes: { nodes: number[] }[] };

const grips: Grip[] = [];
function walk(idx: number, parent: THREE.Matrix4): void {
  const n = gltf.nodes[idx];
  const local = new THREE.Matrix4().compose(
    new THREE.Vector3(...(n.translation ?? [0, 0, 0])),
    new THREE.Quaternion(...((n.rotation ?? [0, 0, 0, 1]) as [number, number, number, number])),
    new THREE.Vector3(...(n.scale ?? [1, 1, 1])),
  );
  const world = parent.clone().multiply(local);
  if (n.name?.startsWith('grip_')) {
    const position = new THREE.Vector3().setFromMatrixPosition(world);
    const q = new THREE.Quaternion().setFromRotationMatrix(world);
    const ex = n.extras ?? {};
    grips.push({
      id: grips.length,
      name: n.name,
      type: (ex.grip_type as GripType) ?? 'jug',
      start: !!ex.start,
      summit: !!ex.summit,
      position,
      normal: new THREE.Vector3(0, 1, 0).applyQuaternion(q),
      node: new THREE.Object3D(),
    });
  }
  for (const c of n.children ?? []) walk(c, world);
}
for (const r of gltf.scenes[0].nodes) walk(r, new THREE.Matrix4());

const climber = new Climber(grips, () => null);
const ap = new Autopilot(climber, grips);
const seconds = Number(secondsArg ?? 300);
const dt = 1 / 60;
let lastLog = -1;
let maxH = 0;
for (let t = 0; t < seconds && climber.state !== 'summit'; t += dt) {
  ap.update(dt);
  climber.update(dt);
  maxH = Math.max(maxH, climber.height);
  if (Math.floor(t / 5) !== lastLog) {
    lastLog = Math.floor(t / 5);
    const h = (s: 'left' | 'right') => {
      const x = climber.hands[s];
      return `${(x.grip ?? x.target)?.name ?? '-'}(${x.stamina.toFixed(2)})`;
    };
    console.log(`t=${t.toFixed(0)}s h=${climber.height.toFixed(2)} L=${h('left')} R=${h('right')} ${climber.state} ${climber.activeMessage}`);
  }
}
console.log(`ERGEBNIS: ${climber.state}, max. Höhe ${maxH.toFixed(1)} m, Zeit ${climber.elapsed.toFixed(1)} s, Stürze ${climber.falls}, Griffe ${grips.length}`);

if (process.env.DEBUG) {
  const sh = climber.shoulder('left');
  console.log('Schulter links', sh.toArray().map((v) => v.toFixed(2)).join(','));
  for (const g of grips.filter((g) => g.position.y > 7.5 && g.position.y < 10.5)) {
    console.log(g.name, g.position.toArray().map((v) => v.toFixed(2)).join(','), 'dL', sh.distanceTo(g.position).toFixed(2), 'dR', climber.shoulder('right').distanceTo(g.position).toFixed(2));
  }
}
