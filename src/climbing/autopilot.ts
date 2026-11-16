import type { Climber, Side } from './climber';
import type { Grip } from './grip';

/**
 * Einfacher Test-Autopilot (nur mit ?autoclimb in der Adresse aktiv):
 * greift abwechselnd mit der hinteren Hand den hoechsten erreichbaren Griff,
 * bevorzugt Henkel und rastet, wenn die Ausdauer knapp wird.
 */
export class Autopilot {
  private cooldown = 0.8;
  private next: Side = 'right';

  constructor(
    private readonly climber: Climber,
    private readonly grips: Grip[],
  ) {}

  update(dt: number): void {
    const c = this.climber;
    if (c.state !== 'climbing') return;
    this.cooldown -= dt;
    if (this.cooldown > 0) return;
    const L = c.hands.left;
    const R = c.hands.right;
    if (!c.holding(L) || !c.holding(R)) return;

    // auf zwei Henkeln rasten, bis die Ausdauer wieder hoch ist
    const resting = L.grip!.type === 'jug' && R.grip!.type === 'jug';
    if (resting && Math.min(L.stamina, R.stamina) < 0.6) return;

    // zuerst zieht die tiefere Hand nach; findet sie nichts, greift die hoehere weiter
    const lower: Side = L.grip!.position.y < R.grip!.position.y - 0.05 ? 'left'
      : R.grip!.position.y < L.grip!.position.y - 0.05 ? 'right' : this.next;
    const higher: Side = lower === 'left' ? 'right' : 'left';
    for (const side of [lower, higher]) {
      const best = this.pick(side);
      if (best && c.grab(side, best)) {
        this.next = higher;
        this.cooldown = 0.45;
        return;
      }
    }
    this.next = higher;
    this.cooldown = 0.2;
  }

  private pick(side: Side): Grip | null {
    const c = this.climber;
    const own = c.hands[side].grip!;
    const other = c.hands[side === 'left' ? 'right' : 'left'].grip!;
    const top = Math.max(own.position.y, other.position.y);
    let best: Grip | null = null;
    let bestScore = -Infinity;
    for (const g of this.grips) {
      if (g === other || g === own || !c.canReach(side, g)) continue;
      const gain = g.position.y - own.position.y;
      if (gain < 0.15) continue; // nur Zuege, die die Hand nach oben bringen
      const dx = g.position.x - other.position.x;
      const wrongSide = side === 'left' ? dx > 0.15 : dx < -0.15; // Ueberkreuzen vermeiden
      const score = (g.position.y - top) * 2 - Math.abs(dx) * 0.5 - (wrongSide ? 0.6 : 0)
        + (g.type === 'jug' ? 0.35 : 0) + (g.summit ? 10 : 0);
      if (score > bestScore) {
        bestScore = score;
        best = g;
      }
    }
    return best;
  }
}
