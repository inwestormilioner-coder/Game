import * as THREE from 'three';
import type { Monster } from '../entities/Monster';

// GDD Section 16 "Map discovery (fog of war)": the minimap only ever shows
// terrain the character has physically walked through, tracked as a coarse
// grid of cells rather than exact coordinates, and is permanent once revealed.
const CELL_SIZE = 2;
const REVEAL_RADIUS = 9;

// GDD Section 10: +/- zoom only rescales already-discovered terrain — it
// never reveals anything new, and it's entirely separate from the fixed
// 3D combat camera (Section 28).
const MIN_VIEW_RADIUS = 15;
const MAX_VIEW_RADIUS = 45;
const ZOOM_STEP = 8;

const MONSTER_DETECT_RANGE = 18;

export class MiniMap {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private discovered = new Set<string>();
  private viewRadius = 25;

  constructor(root: HTMLElement) {
    this.canvas = root.querySelector('#minimap-canvas')!;
    this.ctx = this.canvas.getContext('2d')!;
    root.querySelector('#minimap-zoom-in')!.addEventListener('click', () => this.zoom(-ZOOM_STEP));
    root.querySelector('#minimap-zoom-out')!.addEventListener('click', () => this.zoom(ZOOM_STEP));
  }

  get discoveredCount(): number {
    return this.discovered.size;
  }

  get currentViewRadius(): number {
    return this.viewRadius;
  }

  private zoom(delta: number): void {
    this.viewRadius = Math.min(MAX_VIEW_RADIUS, Math.max(MIN_VIEW_RADIUS, this.viewRadius + delta));
  }

  /** Call every frame the player is alive — marks the area around them as discovered. */
  reveal(playerPos: THREE.Vector3): void {
    const cx = Math.floor(playerPos.x / CELL_SIZE);
    const cz = Math.floor(playerPos.z / CELL_SIZE);
    const r = Math.ceil(REVEAL_RADIUS / CELL_SIZE);
    for (let dx = -r; dx <= r; dx++) {
      for (let dz = -r; dz <= r; dz++) {
        if (dx * dx + dz * dz <= r * r) this.discovered.add(`${cx + dx},${cz + dz}`);
      }
    }
  }

  draw(playerPos: THREE.Vector3, playerFacing: THREE.Vector3, monsters: Monster[]): void {
    const { ctx, canvas } = this;
    const size = canvas.width;
    ctx.clearRect(0, 0, size, size);
    ctx.fillStyle = '#0a0a0a';
    ctx.fillRect(0, 0, size, size);

    const toScreen = (wx: number, wz: number): [number, number] => [
      size / 2 + ((wx - playerPos.x) / this.viewRadius) * (size / 2),
      size / 2 + ((wz - playerPos.z) / this.viewRadius) * (size / 2),
    ];

    const cellPx = (CELL_SIZE / this.viewRadius) * (size / 2);
    ctx.fillStyle = '#2f4f2f';
    for (const key of this.discovered) {
      const [cx, cz] = key.split(',').map(Number);
      const wx = cx * CELL_SIZE + CELL_SIZE / 2;
      const wz = cz * CELL_SIZE + CELL_SIZE / 2;
      if (Math.abs(wx - playerPos.x) > this.viewRadius + CELL_SIZE) continue;
      if (Math.abs(wz - playerPos.z) > this.viewRadius + CELL_SIZE) continue;
      const [sx, sy] = toScreen(wx, wz);
      ctx.fillRect(sx - cellPx / 2, sy - cellPx / 2, cellPx + 1, cellPx + 1);
    }

    ctx.fillStyle = '#e0453f';
    for (const m of monsters) {
      if (!m.alive || m.mesh.position.distanceTo(playerPos) > MONSTER_DETECT_RANGE) continue;
      const [sx, sy] = toScreen(m.mesh.position.x, m.mesh.position.z);
      if (sx < 0 || sx > size || sy < 0 || sy > size) continue;
      ctx.beginPath();
      ctx.arc(sx, sy, 2.5, 0, Math.PI * 2);
      ctx.fill();
    }

    // Player arrow — the map itself stays fixed/north-up (matches the fixed
    // combat camera, Section 28); only the arrow rotates to show facing.
    ctx.save();
    ctx.translate(size / 2, size / 2);
    ctx.rotate(Math.atan2(playerFacing.x, playerFacing.z));
    ctx.fillStyle = '#6cc0e6';
    ctx.beginPath();
    ctx.moveTo(0, -6);
    ctx.lineTo(4, 5);
    ctx.lineTo(-4, 5);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }
}
