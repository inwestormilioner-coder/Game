import * as THREE from 'three';
import type { LootDrop } from '../systems/loot';

export interface CorpseLoot {
  gold: number;
  items: LootDrop[];
}

// GDD Section 12: a kill doesn't hand loot to the killer — it drops a
// corpse that anyone can open, first-come-first-served, until it decays.
const LIFETIME_SECONDS = 60;

export class Corpse {
  readonly mesh: THREE.Mesh;
  readonly loot: CorpseLoot;
  looted = false;
  private lifeTimer = LIFETIME_SECONDS;

  constructor(position: THREE.Vector3, color: number, loot: CorpseLoot) {
    this.loot = loot;
    this.mesh = new THREE.Mesh(
      new THREE.SphereGeometry(0.42, 10, 6),
      new THREE.MeshStandardMaterial({ color, roughness: 1, transparent: true, opacity: 0.75 }),
    );
    this.mesh.scale.set(1.3, 0.32, 1.3);
    this.mesh.position.copy(position);
    this.mesh.position.y = 0.1;
  }

  get expired(): boolean {
    return this.lifeTimer <= 0;
  }

  update(dt: number): void {
    this.lifeTimer -= dt;
  }

  /** First opener wins — call once and trust the caller not to call it again after. */
  open(): CorpseLoot {
    this.looted = true;
    const mat = this.mesh.material as THREE.MeshStandardMaterial;
    mat.opacity = 0.25;
    return this.loot;
  }
}
