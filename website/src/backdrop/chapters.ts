import type { ChapterRenderer, DrawEnv } from './types.ts';
import { C, clamp01, lerp, rgba, rng, smooth } from './util.ts';

/* ---------------------------------------------------------------
 * 01 · Introduction — a horizon of electric blue light and a field
 * of particles that the camera pushes through as you scroll.
 * ------------------------------------------------------------- */
function intro(): ChapterRenderer {
  type P = { x: number; y: number; z: number; gold: boolean };
  let pts: P[] = [];
  const rand = rng(11);
  const spawn = (p: P, far: boolean) => {
    p.x = (rand() * 2 - 1) * 1.4;
    p.y = (rand() * 2 - 1) * 0.9;
    p.z = far ? 0.6 + rand() * 0.4 : 0.05 + rand() * 0.95;
    p.gold = rand() < 0.07;
  };
  return {
    resize(_w, _h, wide) {
      pts = Array.from({ length: wide ? 140 : 80 }, () => {
        const p = { x: 0, y: 0, z: 0, gold: false };
        spawn(p, false);
        return p;
      });
    },
    draw({ ctx, w, h, p: scrolled, t, dt, wide, still }) {
      // Without scroll animation the opening frame is the one to show.
      const p = still ? 0 : scrolled;
      const hy = h * lerp(wide ? 0.78 : 0.84, 0.52, smooth(p));
      // Atmospheric glow over the horizon.
      ctx.save();
      ctx.translate(w / 2, hy);
      ctx.scale(1, 0.32);
      const r = Math.max(w, h) * 0.75;
      const g = ctx.createRadialGradient(0, 0, 0, 0, 0, r);
      g.addColorStop(0, rgba(C.blue, 0.22 + 0.06 * Math.sin(t * 0.4)));
      g.addColorStop(0.45, rgba(C.navy, 0.35));
      g.addColorStop(1, rgba(C.bg, 0));
      ctx.fillStyle = g;
      ctx.fillRect(-r, -r, r * 2, r * 2);
      ctx.restore();

      // Horizon line widening as the camera moves forward.
      const half = w * lerp(0.28, 0.5, smooth(p));
      const lg = ctx.createLinearGradient(w / 2 - half, 0, w / 2 + half, 0);
      lg.addColorStop(0, rgba(C.blue, 0));
      lg.addColorStop(0.5, rgba(C.blue, 0.9));
      lg.addColorStop(1, rgba(C.blue, 0));
      ctx.fillStyle = lg;
      ctx.fillRect(w / 2 - half, hy - 0.5, half * 2, 1);
      ctx.globalCompositeOperation = 'lighter';
      ctx.fillRect(w / 2 - half, hy - 3, half * 2, 6);
      ctx.globalCompositeOperation = 'source-over';

      // Depth particles: forward speed grows with scroll.
      const speed = 0.035 + p * 0.5;
      const fx = w * 0.42;
      const fy = h * 0.32;
      for (const q of pts) {
        q.z -= speed * dt;
        if (q.z < 0.04) spawn(q, true);
        const sx = w / 2 + (q.x / q.z) * fx;
        const sy = hy + (q.y / q.z) * fy;
        if (sx < -20 || sx > w + 20 || sy < -20 || sy > h + 20) {
          if (dt > 0) spawn(q, true);
          continue;
        }
        const near = 1 - q.z;
        const size = 0.4 + near * near * 2.2;
        ctx.fillStyle = rgba(q.gold ? C.gold : C.silver, 0.12 + near * 0.7);
        ctx.fillRect(sx - size / 2, sy - size / 2, size, size);
      }
    },
  };
}

/* ---------------------------------------------------------------
 * 02 · Philosophy — a single shaft of champagne light and one
 * precise horizontal cut. Restraint is the message.
 * ------------------------------------------------------------- */
function philosophy(): ChapterRenderer {
  const rand = rng(23);
  const dust = Array.from({ length: 46 }, () => ({ x: rand() * 2 - 1, y: rand(), s: 0.3 + rand() * 1.2, v: 0.01 + rand() * 0.03 }));
  return {
    draw({ ctx, w, h, p, t, beats, wide }) {
      const peak = beats.reduce((m, b) => Math.max(m, b.in * (1 - b.out)), 0);
      const cx = wide ? w * 0.5 : w * 0.5;
      const k = 0.35 + 0.65 * peak;

      // Wide soft shaft.
      const sw = Math.min(w * 0.42, 260);
      const sg = ctx.createLinearGradient(cx - sw, 0, cx + sw, 0);
      sg.addColorStop(0, rgba(C.gold, 0));
      sg.addColorStop(0.5, rgba(C.gold, 0.09 * k));
      sg.addColorStop(1, rgba(C.gold, 0));
      ctx.fillStyle = sg;
      ctx.fillRect(cx - sw, 0, sw * 2, h);

      // Core line, brightest in the middle of the screen.
      const cg = ctx.createLinearGradient(0, 0, 0, h);
      cg.addColorStop(0, rgba(C.gold, 0));
      cg.addColorStop(0.5, rgba(C.gold, 0.55 * k));
      cg.addColorStop(1, rgba(C.gold, 0));
      ctx.fillStyle = cg;
      ctx.fillRect(cx - 0.5, 0, 1, h);

      // The cut: a silver line drawn across while the headline lands.
      const cut = smooth((p - 0.03) / 0.14) * (1 - smooth((p - 0.3) / 0.08));
      if (cut > 0.001) {
        const y = h * 0.5;
        const x1 = w * smooth((p - 0.03) / 0.14);
        const lg = ctx.createLinearGradient(0, 0, x1, 0);
        lg.addColorStop(0, rgba(C.silver, 0));
        lg.addColorStop(1, rgba(C.silver, 0.8 * cut));
        ctx.fillStyle = lg;
        ctx.fillRect(0, y - 0.5, x1, 1);
      }

      // Dust drifting through the light.
      for (const d of dust) {
        const y = ((d.y + t * d.v) % 1) * h;
        const x = cx + d.x * sw * 0.7;
        const a = (1 - Math.abs(d.x)) * 0.5 * k;
        ctx.fillStyle = rgba(C.gold, a);
        ctx.fillRect(x, y, d.s, d.s);
      }
    },
  };
}

/* ---------------------------------------------------------------
 * 03 · Market — four abstract traces, one per market, each with its
 * own character. Synthetic shapes, not market data.
 * ------------------------------------------------------------- */
function series(kind: number, n: number): number[] {
  const r = rng(101 + kind * 17);
  const out: number[] = [];
  let v = 0.5;
  for (let i = 0; i < n; i++) {
    const x = i / n;
    const noise = r() * 2 - 1;
    if (kind === 0) v += (0.5 - v) * 0.12 + noise * 0.05 + Math.sin(x * 40) * 0.01; // Forex: mean-reverting
    if (kind === 1) v = 0.2 + x * 0.55 + Math.sin(x * 8) * 0.06 + noise * 0.015; // Gold: slow, steady
    if (kind === 2) v += 0.006 + (r() < 0.05 ? -0.08 * r() : 0) + noise * 0.012; // Indices: staircase
    if (kind === 3) v += noise * 0.07 + (r() < 0.03 ? (r() - 0.4) * 0.3 : 0); // Crypto: volatile
    out.push(v);
  }
  const min = Math.min(...out);
  const max = Math.max(...out);
  return out.map((y) => (y - min) / (max - min || 1));
}

function market(): ChapterRenderer {
  const N = 160;
  const lanes = [0, 1, 2, 3].map((k) => series(k, N));
  const labels = ['FX', 'XAU', 'IDX', 'CRYPTO'];
  return {
    draw({ ctx, p, t, beats, stage }) {
      const box = stage.querySelector('.market-viz')?.getBoundingClientRect();
      if (!box || box.width < 10) return;
      const laneH = box.height / 4;
      ctx.font = '500 10px "JetBrains Mono", ui-monospace, monospace';
      ctx.textBaseline = 'top';

      lanes.forEach((ys, i) => {
        const b = beats[i];
        const top = box.top + i * laneH;
        const pad = laneH * 0.2;
        const active = b ? b.in * (1 - b.out) : 0;
        const drawn = b ? clamp01((p - b.start) / Math.max(0.05, b.exit - b.start)) : 1;
        const count = Math.max(2, Math.floor(drawn * (N - 1)) + 1);

        ctx.fillStyle = rgba(C.silver, 0.06);
        ctx.fillRect(box.left, top + laneH - 0.5, box.width, 1);
        ctx.fillStyle = rgba(i === 1 ? C.gold : C.silver, 0.35 + active * 0.6);
        ctx.fillText(labels[i], box.left, top + 4);

        if (drawn <= 0) return;
        const px = (j: number) => box.left + (j / (N - 1)) * box.width;
        const py = (j: number) => top + pad + (1 - ys[j]) * (laneH - pad * 2);
        const tone = i === 1 ? C.gold : C.blue;

        ctx.beginPath();
        ctx.moveTo(px(0), py(0));
        for (let j = 1; j < count; j++) ctx.lineTo(px(j), py(j));
        ctx.lineWidth = 1 + active * 0.6;
        ctx.strokeStyle = active > 0.02 ? rgba(tone, 0.25 + active * 0.75) : rgba(C.muted, 0.32);
        ctx.stroke();

        if (active > 0.05 && count < N) {
          const hx = px(count - 1);
          const hy = py(count - 1);
          const glow = ctx.createRadialGradient(hx, hy, 0, hx, hy, 16);
          glow.addColorStop(0, rgba(tone, 0.6 * active));
          glow.addColorStop(1, rgba(tone, 0));
          ctx.fillStyle = glow;
          ctx.fillRect(hx - 16, hy - 16, 32, 32);
          ctx.fillStyle = rgba(C.silver, active);
          ctx.fillRect(hx - 1.5, hy - 1.5, 3, 3);
          ctx.fillStyle = rgba(tone, 0.12 * active * (0.7 + 0.3 * Math.sin(t * 3)));
          ctx.fillRect(hx - 0.5, box.top, 1, box.height);
        }
      });
    },
  };
}

/* ---------------------------------------------------------------
 * 04 · Community — a network that grows outward from one gold node.
 * ------------------------------------------------------------- */
function community(): ChapterRenderer {
  type Node = { x: number; y: number; at: number; ph: number };
  let nodes: Node[] = [];
  let links: [number, number, number][] = [];
  return {
    resize(w, h, wide) {
      const rand = rng(7);
      const count = wide ? 56 : 34;
      const raw = Array.from({ length: count }, (_, i) => ({
        x: i === 0 ? 0.5 : 0.04 + rand() * 0.92,
        y: i === 0 ? 0.52 : 0.06 + rand() * 0.88,
        ph: rand() * Math.PI * 2,
      }));
      const d0 = (n: { x: number; y: number }) => Math.hypot((n.x - 0.5) * w, (n.y - 0.52) * h);
      raw.sort((a, b) => d0(a) - d0(b));
      nodes = raw.map((n, i) => ({ ...n, at: 0.04 + (i / count) * 0.72 }));
      const maxD = Math.min(w, h) * (wide ? 0.24 : 0.32);
      links = [];
      for (let i = 0; i < nodes.length; i++)
        for (let j = i + 1; j < nodes.length; j++) {
          const d = Math.hypot((nodes[i].x - nodes[j].x) * w, (nodes[i].y - nodes[j].y) * h);
          if (d < maxD) links.push([i, j, 1 - d / maxD]);
        }
    },
    draw({ ctx, w, h, p, t }) {
      const pos = nodes.map((n) => ({
        x: n.x * w + Math.sin(t * 0.25 + n.ph) * 5,
        y: n.y * h + Math.cos(t * 0.21 + n.ph) * 5,
        a: clamp01((p - n.at) * 12),
      }));
      ctx.lineWidth = 1;
      for (const [i, j, s] of links) {
        const a = Math.min(pos[i].a, pos[j].a) * s * 0.28;
        if (a < 0.005) continue;
        ctx.strokeStyle = rgba(C.blue, a);
        ctx.beginPath();
        ctx.moveTo(pos[i].x, pos[i].y);
        ctx.lineTo(pos[j].x, pos[j].y);
        ctx.stroke();
      }
      pos.forEach((q, i) => {
        if (q.a <= 0) return;
        if (i === 0) {
          const r = 26 + Math.sin(t * 1.2) * 4;
          const g = ctx.createRadialGradient(q.x, q.y, 0, q.x, q.y, r);
          g.addColorStop(0, rgba(C.gold, 0.5 * q.a));
          g.addColorStop(1, rgba(C.gold, 0));
          ctx.fillStyle = g;
          ctx.fillRect(q.x - r, q.y - r, r * 2, r * 2);
        }
        const s = i === 0 ? 4 : 2;
        ctx.fillStyle = rgba(i === 0 ? C.gold : C.silver, (i === 0 ? 1 : 0.55) * q.a);
        ctx.fillRect(q.x - s / 2, q.y - s / 2, s, s);
      });
    },
  };
}

/* ---------------------------------------------------------------
 * 05 · Intelligence — a perspective field with a scanning ring; each
 * capability sends a pulse out from the centre as it appears.
 * ------------------------------------------------------------- */
function intelligence(): ChapterRenderer {
  return {
    draw({ ctx, w, h, p, t, beats, wide }) {
      const vx = w / 2;
      const vy = h * (wide ? 0.6 : 0.66);
      const reveal = smooth(p * 3);

      // Floor grid.
      ctx.lineWidth = 1;
      for (let i = -12; i <= 12; i++) {
        ctx.strokeStyle = rgba(C.blue, 0.1 * reveal * (1 - Math.abs(i) / 13));
        ctx.beginPath();
        ctx.moveTo(vx, vy);
        ctx.lineTo(vx + i * w * 0.18, h);
        ctx.stroke();
      }
      const off = (t * 0.08) % 1;
      for (let k = 0; k < 10; k++) {
        const f = (k + off) / 10;
        const y = vy + (h - vy) * f * f;
        ctx.fillStyle = rgba(C.blue, 0.12 * reveal * f);
        ctx.fillRect(0, y, w, 1);
      }

      // Horizon glow.
      const hg = ctx.createLinearGradient(0, vy - 80, 0, vy + 40);
      hg.addColorStop(0, rgba(C.blue, 0));
      hg.addColorStop(0.7, rgba(C.blue, 0.12 * reveal));
      hg.addColorStop(1, rgba(C.blue, 0));
      ctx.fillStyle = hg;
      ctx.fillRect(0, vy - 80, w, 120);

      // Rings + scanning arc.
      const R = Math.min(w * 0.46, 420);
      const rings = 1 + Math.floor(smooth(p * 1.4) * 4);
      for (let k = 1; k <= rings; k++) {
        ctx.strokeStyle = rgba(C.silver, 0.1 - k * 0.012);
        ctx.beginPath();
        ctx.ellipse(vx, vy, (R * k) / 4, (R * k * 0.26) / 4, 0, 0, Math.PI * 2);
        ctx.stroke();
      }
      const a0 = t * 0.7;
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = rgba(C.blue, 0.65 * reveal);
      ctx.beginPath();
      ctx.ellipse(vx, vy, R, R * 0.26, 0, a0, a0 + 0.7);
      ctx.stroke();

      // One pulse per capability.
      for (const b of beats) {
        if (b.in <= 0 || b.in >= 1) continue;
        ctx.lineWidth = 1;
        ctx.strokeStyle = rgba(C.gold, 0.5 * (1 - b.in));
        ctx.beginPath();
        ctx.ellipse(vx, vy, R * b.in * 1.2, R * 0.26 * b.in * 1.2, 0, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.fillStyle = rgba(C.gold, 0.9 * reveal);
      ctx.fillRect(vx - 1.5, vy - 1.5, 3, 3);
    },
  };
}

/* ---------------------------------------------------------------
 * 06 · Final invitation — light converging on the emblem.
 * ------------------------------------------------------------- */
function finale(): ChapterRenderer {
  type S = { a: number; r: number; v: number; gold: boolean };
  let streaks: S[] = [];
  let maxR = 800;
  const rand = rng(5);
  const reset = (s: S, anywhere: boolean) => {
    s.a = rand() * Math.PI * 2;
    s.r = anywhere ? 40 + rand() * maxR : maxR * (0.8 + rand() * 0.4);
    s.v = 0.4 + rand() * 0.8;
    s.gold = rand() < 0.25;
  };
  return {
    resize(w, h, wide) {
      maxR = Math.hypot(w, h) * 0.6;
      streaks = Array.from({ length: wide ? 110 : 70 }, () => {
        const s = { a: 0, r: 0, v: 0, gold: false };
        reset(s, true);
        return s;
      });
    },
    draw({ ctx, w, h, p, dt, stage }) {
      const logo = stage.querySelector('.enter-mark')?.getBoundingClientRect();
      const cx = logo ? logo.left + logo.width / 2 : w / 2;
      const cy = logo ? logo.top + logo.height / 2 : h * 0.38;
      const k = smooth(p * 2);

      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(w, h) * 0.6);
      g.addColorStop(0, rgba(C.gold, 0.16 * k));
      g.addColorStop(0.35, rgba(C.navy, 0.3));
      g.addColorStop(1, rgba(C.bg, 0));
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);

      ctx.lineWidth = 1;
      for (const s of streaks) {
        s.r -= s.v * (60 + 240 * k) * dt;
        if (s.r < 30) reset(s, false);
        const x = cx + Math.cos(s.a) * s.r;
        const y = cy + Math.sin(s.a) * s.r;
        const len = 6 + 28 * k * (s.r / maxR);
        const x2 = cx + Math.cos(s.a) * (s.r + len);
        const y2 = cy + Math.sin(s.a) * (s.r + len);
        ctx.strokeStyle = rgba(s.gold ? C.gold : C.silver, 0.12 + 0.5 * (1 - s.r / maxR) * k);
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
    },
  };
}

export const CHAPTERS: Record<string, () => ChapterRenderer> = {
  intro,
  philosophy,
  market,
  community,
  intelligence,
  enter: finale,
};

export type { DrawEnv };
