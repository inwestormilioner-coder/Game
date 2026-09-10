import * as THREE from 'three';
import type { GatherNodeDef } from '../data/gathering';

const KIND_COLOR: Record<string, number> = {
  mining: 0x8899a0,
  woodcutting: 0x5a8f4a,
  fishing: 0x4a90c0,
};

/** A mining vein / tree / fishing spot the player can gather from (gathering professions). */
export class GatherNode {
  readonly mesh: THREE.Mesh;
  readonly def: GatherNodeDef;
  depleted = false;
  private respawnTimer = 0;

  constructor(def: GatherNodeDef) {
    this.def = def;
    // Tier 2 nodes read as richer/darker so a "harder mine/tree/spot" looks the part.
    const color = def.tier >= 2 ? shade(KIND_COLOR[def.kind], 0.65) : KIND_COLOR[def.kind];
    const material = new THREE.MeshStandardMaterial({ color, roughness: 0.85 });

    if (def.kind === 'mining') {
      this.mesh = new THREE.Mesh(new THREE.DodecahedronGeometry(0.55 + def.tier * 0.15, 0), material);
      this.mesh.position.set(def.x, 0.4, def.z);
      this.mesh.castShadow = true;
    } else if (def.kind === 'woodcutting') {
      this.mesh = new THREE.Mesh(new THREE.ConeGeometry(0.7, 2.2, 8), material);
      this.mesh.position.set(def.x, 1.1, def.z);
      this.mesh.castShadow = true;
    } else {
      this.mesh = new THREE.Mesh(new THREE.CircleGeometry(0.6, 20), material);
      this.mesh.rotation.x = -Math.PI / 2;
      this.mesh.position.set(def.x, 0.03, def.z);
    }
  }

  distanceTo(pos: THREE.Vector3): number {
    return this.mesh.position.distanceTo(pos);
  }

  deplete(): void {
    this.depleted = true;
    this.respawnTimer = this.def.respawnDelay;
    this.mesh.visible = false;
  }

  update(dt: number): void {
    if (!this.depleted) return;
    this.respawnTimer -= dt;
    if (this.respawnTimer <= 0) {
      this.depleted = false;
      this.mesh.visible = true;
    }
  }
}

function shade(hex: number, factor: number): number {
  const r = Math.round(((hex >> 16) & 0xff) * factor);
  const g = Math.round(((hex >> 8) & 0xff) * factor);
  const b = Math.round((hex & 0xff) * factor);
  return (r << 16) | (g << 8) | b;
}
