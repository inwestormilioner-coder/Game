import type { ScrubFrame } from '../scrub/types.ts';
import { rangeProgress } from '../scrub/ScrollScrub.ts';
import type { Beat, ChapterRenderer } from './types.ts';
import { CHAPTERS } from './chapters.ts';
import { C } from './util.ts';

interface Slot {
  renderer: ChapterRenderer;
  beatEls: HTMLElement[];
}

const range = (attr?: string): [number, number] | null => {
  if (!attr) return null;
  const [a, b] = attr.split(/[\s,]+/).map(Number);
  return Number.isFinite(a) && Number.isFinite(b) ? [a, b] : null;
};

/**
 * One fixed full-screen canvas behind the page. Every chapter has its own
 * renderer; chapters cross-dissolve according to how much of the viewport
 * their stage covers, so scrolling reads as one continuous shot.
 */
export class Backdrop {
  private ctx: CanvasRenderingContext2D;
  private slots = new Map<string, Slot>();
  private frame: ScrubFrame | null = null;
  private w = 0;
  private h = 0;
  private wide = false;
  private t = 0;
  private last = 0;
  private running = false;
  private motion = matchMedia('(prefers-reduced-motion: reduce)');

  private canvas: HTMLCanvasElement;

  private constructor(canvas: HTMLCanvasElement, ctx: CanvasRenderingContext2D) {
    this.canvas = canvas;
    this.ctx = ctx;
    for (const [id, make] of Object.entries(CHAPTERS)) {
      const stage = document.querySelector(`[data-scene="${id}"] .stage`);
      this.slots.set(id, { renderer: make(), beatEls: stage ? [...stage.querySelectorAll<HTMLElement>('[data-beat]')] : [] });
    }
    this.resize();
    addEventListener('resize', this.resize);
    document.addEventListener('visibilitychange', this.syncLoop);
    this.motion.addEventListener('change', this.syncLoop);
  }

  /** Returns null (and flags the page) when 2D canvas is unavailable. */
  static create(canvas: HTMLCanvasElement | null): Backdrop | null {
    const ctx = canvas?.getContext('2d', { alpha: false });
    if (!canvas || !ctx) {
      document.documentElement.classList.add('no-canvas');
      return null;
    }
    return new Backdrop(canvas, ctx);
  }

  update = (frame: ScrubFrame) => {
    this.frame = frame;
    if (!this.running) this.draw(0);
    this.syncLoop();
  };

  private get animated() {
    return !this.motion.matches && document.visibilityState === 'visible';
  }

  private syncLoop = () => {
    if (this.animated && !this.running) {
      this.running = true;
      this.last = performance.now();
      requestAnimationFrame(this.tick);
    }
  };

  private tick = (now: number) => {
    if (!this.animated) {
      this.running = false;
      return;
    }
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    this.t += dt;
    this.draw(dt);
    requestAnimationFrame(this.tick);
  };

  private resize = () => {
    this.wide = innerWidth >= 900;
    const dpr = Math.min(devicePixelRatio || 1, this.wide ? 2 : 1.5);
    this.w = innerWidth;
    this.h = innerHeight;
    this.canvas.width = Math.round(this.w * dpr);
    this.canvas.height = Math.round(this.h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.slots.forEach((s) => s.renderer.resize?.(this.w, this.h, this.wide));
    if (!this.running) this.draw(0);
  };

  private beats(slot: Slot, p: number, isStatic: boolean): Beat[] {
    return slot.beatEls.map((el) => {
      const r1 = range(el.dataset.in);
      const r2 = range(el.dataset.out);
      return {
        in: isStatic || !r1 ? 1 : rangeProgress(p, r1),
        out: isStatic || !r2 ? 0 : rangeProgress(p, r2),
        start: r1?.[0] ?? 0,
        end: r1?.[1] ?? 0,
        exit: r2?.[0] ?? 1,
      };
    });
  }

  private draw(dt: number) {
    const { ctx, w, h } = this;
    ctx.globalAlpha = 1;
    ctx.fillStyle = `rgb(${C.bg.join(',')})`;
    ctx.fillRect(0, 0, w, h);
    const frame = this.frame;
    if (!frame) return;

    for (const scene of frame.scenes) {
      if (scene.visibility < 0.005) continue;
      const slot = this.slots.get(scene.id);
      if (!slot) continue;
      ctx.save();
      ctx.globalAlpha = scene.visibility;
      slot.renderer.draw({
        ctx,
        w,
        h,
        t: this.t,
        dt: this.animated ? dt : 0,
        p: scene.progress,
        wide: this.wide,
        still: frame.static,
        stage: scene.stage,
        beats: this.beats(slot, scene.progress, frame.static),
      });
      ctx.restore();
    }
  }
}
