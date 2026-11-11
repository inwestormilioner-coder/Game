import type { SceneConfig } from './types.ts';

/**
 * The six chapters, in scroll order. `length` is the pinned travel in
 * viewport heights: longer chapters hold more beats.
 *
 * No chapter has video footage yet, so `media` is omitted and the canvas
 * backdrop (src/backdrop) renders each chapter. To add footage later, put
 * the file in src/assets, import it here and set e.g.
 * `media: { src: introVideo, type: 'video/mp4' }`.
 */
export const SCENES: readonly SceneConfig[] = [
  { id: 'intro', length: { base: 1.6, wide: 1.7 } },
  { id: 'philosophy', length: { base: 4.2, wide: 4 } },
  { id: 'market', length: { base: 4, wide: 3.6 } },
  { id: 'community', length: { base: 3.8, wide: 3.4 } },
  { id: 'intelligence', length: { base: 3.6, wide: 3.2 } },
  { id: 'enter', length: { base: 1.7, wide: 1.7 } },
];
