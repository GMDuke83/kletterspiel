import * as THREE from 'three';

/** Gipfelbuch-Eintrag (lokal im Browser gespeichert) */
export interface SummitEntry {
  date: string;
  seconds: number;
  falls: number;
}

const BOOK_KEY = 'gipfelbuch-dufourspitze';

export function readSummitBook(): SummitEntry[] {
  try {
    return JSON.parse(localStorage.getItem(BOOK_KEY) ?? '[]') as SummitEntry[];
  } catch {
    return [];
  }
}

export function addSummitEntry(e: SummitEntry): SummitEntry[] {
  const book = [e, ...readSummitBook()].slice(0, 20);
  try {
    localStorage.setItem(BOOK_KEY, JSON.stringify(book));
  } catch {
    /* ohne Speicher kein Gipfelbuch */
  }
  return book;
}

/** Steinmaenner entlang des Gratwegs und ein Gipfelkreuz. */
export function buildRouteMarkers(points: number[][], ground: (x: number, z: number) => number): THREE.Group {
  const g = new THREE.Group();
  const stone = new THREE.MeshStandardMaterial({ color: 0x8a8580, roughness: 0.95 });
  const geo = new THREE.DodecahedronGeometry(1, 0);
  for (let i = 4; i < points.length - 2; i += 4) { // etwa alle 10 m ein Steinmann
    const [x, , z] = points[i];
    const y = ground(x, z);
    if (!Number.isFinite(y)) continue;
    // drei gestapelte Steine
    [0.16, 0.12, 0.08].reduce((h, r, k) => {
      const m = new THREE.Mesh(geo, stone);
      m.scale.set(r * 1.2, r * 0.8, r);
      m.rotation.set(k * 0.7, k * 1.3, 0.2 * k);
      m.position.set(x, y + h + r * 0.7, z);
      m.castShadow = true;
      g.add(m);
      return h + r * 1.4;
    }, 0);
  }
  // Gipfelkreuz
  const [sx, , sz] = points[points.length - 1];
  const sy = ground(sx, sz);
  const metal = new THREE.MeshStandardMaterial({ color: 0xb8b8b8, metalness: 0.8, roughness: 0.35 });
  const post = new THREE.Mesh(new THREE.BoxGeometry(0.1, 2.4, 0.1), metal);
  post.position.set(sx, sy + 1.2, sz);
  const bar = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.1, 0.1), metal);
  bar.position.set(sx, sy + 1.75, sz);
  post.castShadow = bar.castShadow = true;
  g.add(post, bar);
  return g;
}

export function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const r = Math.round(s % 60);
  return `${m}:${String(r).padStart(2, '0')} min`;
}
