import * as THREE from 'three';
import type { NpcDef } from '../data/npcs';

/** Static, non-hostile world characters (GDD Section 17) — dialogue/quest/depot/ferryman roles. */
export class Npc {
  readonly mesh: THREE.Group;
  readonly def: NpcDef;

  constructor(def: NpcDef) {
    this.def = def;
    this.mesh = new THREE.Group();

    const body = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.35, 0.9, 4, 8),
      new THREE.MeshStandardMaterial({ color: def.color }),
    );
    body.position.y = 0.8;
    body.castShadow = true;

    const head = new THREE.Mesh(
      new THREE.SphereGeometry(0.26, 12, 12),
      new THREE.MeshStandardMaterial({ color: 0xffd9b3 }),
    );
    head.position.y = 1.5;
    head.castShadow = true;

    this.mesh.add(body, head);
    this.mesh.position.set(def.x, 0, def.z);
  }

  distanceTo(pos: THREE.Vector3): number {
    return this.mesh.position.distanceTo(pos);
  }
}
