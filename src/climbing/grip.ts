import * as THREE from 'three';

export type GripType = 'jug' | 'crimp' | 'sloper';

export interface Grip {
  id: number;
  name: string;
  type: GripType;
  start: boolean;
  summit: boolean;
  /** Greifpunkt in Weltkoordinaten */
  position: THREE.Vector3;
  /** Flaechennormale (zeigt von der Wand weg) */
  normal: THREE.Vector3;
  node: THREE.Object3D;
}

export interface GripInfo {
  label: string;
  color: number;
  /** Ausdauerverlust pro Sekunde beim Halten (senkrechte Wand, beide Haende) */
  drain: number;
}

export const GRIP_INFO: Record<GripType, GripInfo> = {
  jug: { label: 'Henkel', color: 0x4cd964, drain: 0.025 },
  crimp: { label: 'Leiste', color: 0xffcc00, drain: 0.08 },
  sloper: { label: 'Sloper', color: 0x4aa3ff, drain: 0.1 },
};

/** 0 = senkrecht/geneigt, 1 = Dach. Ueberhang heisst: die Flaeche schaut nach unten. */
export function overhangAmount(g: Grip): number {
  return Math.max(0, -g.normal.y);
}
