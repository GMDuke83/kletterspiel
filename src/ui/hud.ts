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
  private alt = el('alt');
  private time = el('time');
  private falls = el('falls');
  private msg = el('msg');
  private hover = el('hover');
  private overlay = el('overlay');
  private overlayText = el('overlayText');
  private overlayTitle = el('overlayTitle');
  private hint = el('hint');
  private mode = el('mode');
  /** Etappen-Modus: das Wand-Ende ist nicht das Spielende */
  stageMode = false;

  /** Hinweis unten in der Bildmitte (z. B. "F = einsteigen") */
  setHint(text: string): void {
    this.hint.textContent = text;
    this.hint.hidden = !text;
  }

  setMode(text: string): void {
    this.mode.textContent = text;
  }

  /** Abschluss-Bildschirm (Etappe geschafft); null = ausblenden */
  showOverlay(title: string | null, text = ''): void {
    this.overlay.hidden = title === null;
    if (title !== null) {
      this.overlayTitle.textContent = title;
      this.overlayText.innerHTML = text;
    }
  }

  /** Anzeige im Gehmodus: Puste statt Hand-Ausdauer */
  updateWalk(stamina: number, terrain: string, altitude: number, time: number, falls: number, message: string): void {
    for (const side of ['left', 'right'] as Side[]) {
      this.bars[side].style.width = `${Math.round(stamina * 100)}%`;
      this.bars[side].classList.toggle('low', stamina < 0.25);
      this.gripLabels[side].textContent = side === 'left' ? 'Puste' : terrain;
    }
    this.height.textContent = '–';
    this.alt.textContent = `${Math.round(altitude).toLocaleString('de-CH')} m ü. M.`;
    this.time.textContent = `${time.toFixed(0)} s`;
    this.falls.textContent = String(falls);
    this.msg.textContent = message;
    this.hover.textContent = '';
  }

  update(c: Climber, hovered: Grip | null, reachable: boolean, altitude: number): void {
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
    this.alt.textContent = Number.isFinite(altitude) ? `${Math.round(altitude).toLocaleString('de-CH')} m ü. M.` : 'Testwand';
    this.time.textContent = `${c.elapsed.toFixed(1)} s`;
    this.falls.textContent = String(c.falls);
    this.msg.textContent = c.activeMessage;
    this.hover.textContent = hovered
      ? `${hovered.summit ? 'Gipfel' : GRIP_INFO[hovered.type].label}${reachable ? '' : ' (zu weit)'}`
      : '';
    if (!this.stageMode) {
      const won = c.state === 'summit';
      this.showOverlay(won ? 'Gipfel erreicht!' : null, `Zeit: ${c.elapsed.toFixed(1)} s · Stürze: ${c.falls}<br>Drücke <b>R</b> für einen neuen Versuch.`);
    }
  }
}
