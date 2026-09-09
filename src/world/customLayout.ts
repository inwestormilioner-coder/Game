import type { Obstacle } from './World';

/** Hand-authored tree/rock placement, built with the in-game map editor ('M' in a dev
 * build — src/editor/MapEditor.ts). Empty by default, which leaves World.ts's original
 * seeded-random scatter in charge. Paste the editor's exported array here (replacing the
 * empty array below) to switch the world over to your own layout. */
export const CUSTOM_OBSTACLES: Obstacle[] = [];
