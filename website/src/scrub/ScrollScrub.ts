import type { SceneConfig, SceneState, ScrubFrame, ScrubListener } from './types.ts';
import { attachSceneMedia } from './media.ts';

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
const smooth = (v: number) => v * v * (3 - 2 * v);

/** Parses "0.1 0.3" into a [start, end] range. */
function parseRange(attr: string | null): [number, number] | null {
  if (!attr) return null;
  const [a, b] = attr.trim().split(/[\s,]+/).map(Number);
  return Number.isFinite(a) && Number.isFinite(b) && b > a ? [a, b] : null;
}

export const rangeProgress = (p: number, [a, b]: [number, number]) => smooth(clamp01((p - a) / (b - a)));

interface FxTarget {
  el: HTMLElement;
  inRange: [number, number] | null;
  outRange: [number, number] | null;
  last: string;
}

interface SceneRuntime extends SceneState {
  config: SceneConfig;
  fx: FxTarget[];
  lastP: string;
}

/**
 * Scroll-scrub engine.
 *
 * Reads layout once per animation frame (only while the page scrolls or
 * resizes), turns each pinned section into a 0→1 progress value and
 * writes the result to CSS custom properties. Elements opt in with
 * `data-in="start end"` and/or `data-out="start end"` (fractions of the
 * scene's progress); CSS decides what the values look like.
 *
 * With `prefers-reduced-motion: reduce` the engine runs in static mode:
 * sections are not pinned, every element is fully visible and only the
 * active-scene signal is emitted (for navigation and the backdrop).
 */
export class ScrollScrub {
  private scenes: SceneRuntime[] = [];
  private listeners = new Set<ScrubListener>();
  private queued = false;
  private wide = matchMedia('(min-width: 900px)');
  private motion = matchMedia('(prefers-reduced-motion: reduce)');
  private root = document.documentElement;
  isStatic = false;

  constructor(configs: readonly SceneConfig[]) {
    configs.forEach((config, index) => {
      const el = document.querySelector<HTMLElement>(`[data-scene="${config.id}"]`);
      const stage = el?.querySelector<HTMLElement>('.stage');
      if (!el || !stage) {
        console.warn(`[scrub] scene "${config.id}" has no matching section or .stage`);
        return;
      }
      const fx = [...el.querySelectorAll<HTMLElement>('[data-in], [data-out]')].map((node) => ({
        el: node,
        inRange: parseRange(node.dataset.in ?? null),
        outRange: parseRange(node.dataset.out ?? null),
        last: '',
      }));
      if (config.media) attachSceneMedia(stage, config.media, () => this.sceneProgress(config.id));
      this.scenes.push({ id: config.id, index, el, stage, config, fx, progress: 0, visibility: 0, lastP: '' });
    });

    this.applyMode();
    addEventListener('scroll', this.queue, { passive: true });
    addEventListener('resize', this.queue);
    this.wide.addEventListener('change', this.applyMode);
    this.motion.addEventListener('change', this.applyMode);
  }

  get states(): readonly SceneState[] {
    return this.scenes;
  }

  subscribe(fn: ScrubListener): () => void {
    this.listeners.add(fn);
    fn(this.frame());
    return () => this.listeners.delete(fn);
  }

  sceneProgress(id: string): number {
    return this.scenes.find((s) => s.id === id)?.progress ?? 0;
  }

  /** Re-applies lengths and pinning when the viewport class or motion preference changes. */
  private applyMode = () => {
    this.isStatic = this.motion.matches;
    this.root.classList.toggle('scrub', !this.isStatic);
    for (const s of this.scenes) {
      const len = this.wide.matches ? (s.config.length.wide ?? s.config.length.base) : s.config.length.base;
      s.el.style.setProperty('--len', String(len));
      s.lastP = '';
      s.fx.forEach((f) => (f.last = ''));
    }
    if (this.isStatic) this.clearFx();
    this.queue();
  };

  private clearFx() {
    for (const s of this.scenes) {
      s.el.style.removeProperty('--p');
      for (const f of s.fx) ['--in', '--out', '--v'].forEach((k) => f.el.style.removeProperty(k));
    }
  }

  private queue = () => {
    if (this.queued) return;
    this.queued = true;
    requestAnimationFrame(this.update);
  };

  private update = () => {
    this.queued = false;
    const vh = innerHeight;

    for (const s of this.scenes) {
      const r = s.el.getBoundingClientRect();
      const sr = s.stage.getBoundingClientRect();
      s.visibility = clamp01((Math.min(sr.bottom, vh) - Math.max(sr.top, 0)) / vh);

      if (this.isStatic) {
        s.progress = 1;
        continue;
      }
      const travel = r.height - sr.height;
      s.progress = travel > 1 ? clamp01(-r.top / travel) : r.top <= 0 ? 1 : 0;

      const pStr = s.progress.toFixed(4);
      if (pStr !== s.lastP) {
        s.lastP = pStr;
        s.el.style.setProperty('--p', pStr);
      }
      for (const f of s.fx) {
        const vin = f.inRange ? rangeProgress(s.progress, f.inRange) : 1;
        const vout = f.outRange ? rangeProgress(s.progress, f.outRange) : 0;
        const key = `${vin.toFixed(3)}|${vout.toFixed(3)}`;
        if (key === f.last) continue;
        f.last = key;
        f.el.style.setProperty('--in', vin.toFixed(3));
        f.el.style.setProperty('--out', vout.toFixed(3));
        f.el.style.setProperty('--v', (vin * (1 - vout)).toFixed(3));
      }
    }

    const frame = this.frame();
    this.listeners.forEach((fn) => fn(frame));
  };

  private frame(): ScrubFrame {
    let active = 0;
    let best = -1;
    for (const s of this.scenes) {
      if (s.visibility > best) {
        best = s.visibility;
        active = s.index;
      }
    }
    const max = document.documentElement.scrollHeight - innerHeight;
    return { scenes: this.scenes, active, overall: max > 0 ? clamp01(scrollY / max) : 0, static: this.isStatic };
  }
}
