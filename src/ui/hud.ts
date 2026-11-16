import type { Climber, Side } from '../climbing/climber';
import { GRIP_INFO, type Grip } from '../climbing/grip';

function el<T extends HTMLElement>(id: string): T {
  const e = document.getElementById(id);
  if (!e) throw new Error(`#${id} fehlt in index.html`);
  return e as T;
}

/** Ausdauer-Leisten, Hoehe, Zeit, Meldungen. */
export class Hud {
  private bars = { left: el('barL'), right: el('barR') };
  private gripLabels = { left: el('gripL'), right: el('gripR') };
  private height = el('height');
  private time = el('time');
  private falls = el('falls');
  private msg = el('msg');
  private hover = el('hover');
  private overlay = el('overlay');
  private overlayText = el('overlayText');

  update(c: Climber, hovered: Grip | null, reachable: boolean): void {
    for (const side of ['left', 'right'] as Side[]) {
      const h = c.hands[side];
      const pct = Math.round(h.stamina * 100);
      this.bars[side].style.width = `${pct}%`;
      this.bars[side].classList.toggle('low', h.stamina < 0.25);
      this.gripLabels[side].textContent = h.grip
        ? GRIP_INFO[h.grip.type].label
        : h.target
          ? '…'
          : 'frei';
    }
    this.height.textContent = `${c.height.toFixed(1)} m`;
    this.time.textContent = `${c.elapsed.toFixed(1)} s`;
    this.falls.textContent = String(c.falls);
    this.msg.textContent = c.activeMessage;
    this.hover.textContent = hovered
      ? `${hovered.summit ? 'Gipfel' : GRIP_INFO[hovered.type].label}${reachable ? '' : ' (zu weit)'}`
      : '';
    const won = c.state === 'summit';
    this.overlay.hidden = !won;
    if (won) {
      this.overlayText.textContent = `Zeit: ${c.elapsed.toFixed(1)} s · Stürze: ${c.falls}`;
    }
  }
}
