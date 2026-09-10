import * as THREE from 'three';
import type { Monster } from '../entities/Monster';

const HIDE_MARGIN = 60;

interface Entry {
  monster: Monster;
  root: HTMLElement;
  fill: HTMLElement;
}

/**
 * Floating name + HP bar above each monster, screen-projected every frame — this is the actual
 * "you're targeting this" feedback (the mesh's own subtle opacity/emissive tint alone wasn't
 * legible on a real device). One label per monster, created once and reused for its lifetime.
 */
export class MonsterLabels {
  private container: HTMLElement;
  private entries: Entry[] = [];

  constructor(root: HTMLElement, monsters: Monster[]) {
    this.container = root.querySelector('#monster-labels')!;

    for (const monster of monsters) {
      const labelRoot = document.createElement('div');
      labelRoot.className = 'monster-label';

      const name = document.createElement('div');
      name.className = 'monster-label-name';
      name.textContent = monster.def.name;

      const bar = document.createElement('div');
      bar.className = 'monster-label-bar';
      const fill = document.createElement('div');
      fill.className = 'monster-label-fill';
      bar.appendChild(fill);

      labelRoot.append(name, bar);
      this.container.appendChild(labelRoot);
      this.entries.push({ monster, root: labelRoot, fill });
    }
  }

  update(camera: THREE.Camera, target: Monster | null, viewportWidth: number, viewportHeight: number): void {
    for (const entry of this.entries) {
      const { monster, root } = entry;
      if (!monster.alive) {
        root.style.display = 'none';
        continue;
      }

      const worldPos = monster.mesh.position.clone();
      worldPos.y += monster.def.radius + 0.5;
      const ndc = worldPos.project(camera);

      if (ndc.z > 1) {
        root.style.display = 'none';
        continue;
      }

      const x = (ndc.x * 0.5 + 0.5) * viewportWidth;
      const y = (1 - (ndc.y * 0.5 + 0.5)) * viewportHeight;
      if (x < -HIDE_MARGIN || x > viewportWidth + HIDE_MARGIN || y < -HIDE_MARGIN || y > viewportHeight + HIDE_MARGIN) {
        root.style.display = 'none';
        continue;
      }

      root.style.display = '';
      root.style.transform = `translate(-50%, -100%) translate(${x}px, ${y}px)`;
      entry.fill.style.width = `${Math.max(0, Math.min(100, (monster.hp / monster.maxHp) * 100))}%`;
      root.classList.toggle('targeted', monster === target);
    }
  }
}
