import * as THREE from 'three';
import { CLASSES, type Stats } from '../types';

const HIDE_MARGIN = 60;

/**
 * Floating nickname + mini HP bar above the player's own character (mobile-MOBA/Tibia
 * reference), screen-projected every frame — same technique as MonsterLabels. There's no
 * player-chosen nickname system yet (that needs a naming step, likely tied to accounts/
 * multiplayer, which is still deferred), so the class name stands in for now.
 */
export class PlayerLabel {
  private root: HTMLElement;
  private name: HTMLElement;
  private fill: HTMLElement;

  constructor(rootEl: HTMLElement) {
    this.root = rootEl.querySelector('#player-label')!;

    const labelRoot = document.createElement('div');
    labelRoot.className = 'monster-label';

    this.name = document.createElement('div');
    this.name.className = 'monster-label-name';

    const bar = document.createElement('div');
    bar.className = 'monster-label-bar';
    this.fill = document.createElement('div');
    this.fill.className = 'monster-label-fill';
    bar.appendChild(this.fill);

    labelRoot.append(this.name, bar);
    this.root.appendChild(labelRoot);
    this.root = labelRoot;
  }

  update(camera: THREE.Camera, playerPosition: THREE.Vector3, stats: Stats, viewportWidth: number, viewportHeight: number): void {
    this.name.textContent = CLASSES[stats.classId].name;
    this.fill.style.width = `${Math.max(0, Math.min(100, (stats.hp / stats.maxHp) * 100))}%`;

    const worldPos = playerPosition.clone();
    worldPos.y += 1.9;
    const ndc = worldPos.project(camera);

    if (ndc.z > 1) {
      this.root.style.display = 'none';
      return;
    }

    const x = (ndc.x * 0.5 + 0.5) * viewportWidth;
    const y = (1 - (ndc.y * 0.5 + 0.5)) * viewportHeight;
    if (x < -HIDE_MARGIN || x > viewportWidth + HIDE_MARGIN || y < -HIDE_MARGIN || y > viewportHeight + HIDE_MARGIN) {
      this.root.style.display = 'none';
      return;
    }

    this.root.style.display = '';
    this.root.style.transform = `translate(-50%, -100%) translate(${x}px, ${y}px)`;
  }
}
