export type RGB = readonly [number, number, number];

/** Brand palette as RGB triplets for canvas drawing (mirrors tokens.css). */
export const C = {
  bg: [8, 10, 15],
  navy: [13, 20, 33],
  surface: [23, 34, 53],
  gold: [198, 161, 91],
  blue: [91, 143, 232],
  silver: [216, 222, 232],
  muted: [125, 135, 152],
} as const satisfies Record<string, RGB>;

export const rgba = (c: RGB, a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a < 0 ? 0 : a > 1 ? 1 : a})`;
export const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const smooth = (v: number) => {
  const c = clamp01(v);
  return c * c * (3 - 2 * c);
};

/** Small deterministic PRNG so every visit draws the same composition. */
export function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
