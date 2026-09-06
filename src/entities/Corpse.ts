import * as THREE from 'three';
import type { LootDrop } from '../systems/loot';

export interface CorpseLoot {
  gold: number;
  items: LootDrop[];
}

// GDD Section 12: a kill doesn't hand loot to the killer — it drops a
// corpse that anyone can open, first-come-first-served, until it decays.
// Opening only collects the (weightless) gold; each item still has to be
// individually taken, checked against carry capacity (Section 2.5).
const LIFETIME_SECONDS = 60;

export class Corpse {
  readonly mesh: THREE.Mesh;
  readonly monsterName: string;
  readonly loot: CorpseLoot;
  private lifeTimer = LIFETIME_SECONDS;

  constructor(monsterName: string, position: THREE.Vector3, color: number, loot: CorpseLoot) {
    this.monsterName = monsterName;
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

  /** Nothing left to take — gold already collected and every item already claimed. */
  get hasLoot(): boolean {
    return this.loot.gold > 0 || this.loot.items.length > 0;
  }

  update(dt: number): void {
    this.lifeTimer -= dt;
  }

  /** Collects the gold (idempotent — returns 0 if it was already taken). */
  collectGold(): number {
    const gold = this.loot.gold;
    this.loot.gold = 0;
    if (gold > 0) this.dimIfEmpty();
    return gold;
  }

  peekItem(itemId: string): LootDrop | undefined {
    return this.loot.items.find((i) => i.itemId === itemId);
  }

  /** Removes and returns the item stack, or null if it's already gone (someone beat you to it). */
  takeItem(itemId: string): LootDrop | null {
    const idx = this.loot.items.findIndex((i) => i.itemId === itemId);
    if (idx < 0) return null;
    const [drop] = this.loot.items.splice(idx, 1);
    this.dimIfEmpty();
    return drop;
  }

  private dimIfEmpty(): void {
    if (this.hasLoot) return;
    (this.mesh.material as THREE.MeshStandardMaterial).opacity = 0.25;
  }
}
