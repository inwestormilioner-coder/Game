import * as THREE from 'three';
import { CUSTOM_OBSTACLES } from './customLayout';
import { createPropSprite, PROPS } from './props';

export const WORLD_RADIUS = 40;

/** A solid, roughly-circular thing in the world the player can't walk through.
 * type 'prop' renders as a billboard sprite (see props.ts) — propId picks which one. */
export interface Obstacle {
  type: 'tree' | 'rock' | 'prop';
  x: number;
  z: number;
  radius: number;
  propId?: keyof typeof PROPS;
}

function addTreeMesh(scene: THREE.Scene, x: number, z: number, treeMat: THREE.Material, trunkMat: THREE.Material): void {
  const tree = new THREE.Group();
  const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.2, 1.2, 6), trunkMat);
  trunk.position.y = 0.6;
  const foliage = new THREE.Mesh(new THREE.ConeGeometry(0.9, 2, 8), treeMat);
  foliage.position.y = 1.8;
  tree.add(trunk, foliage);
  tree.position.set(x, 0, z);
  tree.castShadow = true;
  scene.add(tree);
}

function addRockMesh(scene: THREE.Scene, x: number, z: number, radius: number, rockMat: THREE.Material): void {
  const rock = new THREE.Mesh(new THREE.DodecahedronGeometry(radius, 0), rockMat);
  rock.position.set(x, 0.25, z);
  rock.castShadow = true;
  scene.add(rock);
}

function addPropSprite(scene: THREE.Scene, x: number, z: number, propId: string): void {
  const sprite = createPropSprite(propId);
  sprite.position.set(x, 0, z);
  scene.add(sprite);
}

/** Flat open-world ground with scattered rocks/trees so it reads as a world, not a void.
 * Returns the solid obstacles (trees/rocks) so Game.ts can block movement through them.
 * Uses the hand-authored CUSTOM_OBSTACLES layout (src/world/customLayout.ts, built via the
 * in-game map editor — 'M' in a dev build) once it's non-empty; falls back to the original
 * seeded-random scatter until then, so an empty layout file changes nothing. */
export function buildWorld(scene: THREE.Scene): Obstacle[] {
  const ground = new THREE.Mesh(
    new THREE.CircleGeometry(WORLD_RADIUS, 64),
    new THREE.MeshStandardMaterial({ color: 0x3a5f3a, roughness: 1 }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);

  const grid = new THREE.GridHelper(WORLD_RADIUS * 2, 40, 0x264d26, 0x264d26);
  (grid.material as THREE.Material).opacity = 0.25;
  (grid.material as THREE.Material).transparent = true;
  scene.add(grid);

  // A small pond so the fishing spots (gathering professions) have water to sit on.
  const pond = new THREE.Mesh(
    new THREE.CircleGeometry(6, 32),
    new THREE.MeshStandardMaterial({ color: 0x2c6f96, roughness: 0.3, metalness: 0.1 }),
  );
  pond.rotation.x = -Math.PI / 2;
  pond.position.set(19.5, 0.01, 19);
  scene.add(pond);

  const treeMat = new THREE.MeshStandardMaterial({ color: 0x2d5a2d });
  const trunkMat = new THREE.MeshStandardMaterial({ color: 0x5a3d20 });
  const rockMat = new THREE.MeshStandardMaterial({ color: 0x777777, roughness: 0.9 });

  const obstacles: Obstacle[] = [];

  if (CUSTOM_OBSTACLES.length > 0) {
    for (const o of CUSTOM_OBSTACLES) {
      if (o.type === 'prop' && o.propId) addPropSprite(scene, o.x, o.z, o.propId);
      else if (o.type === 'tree') addTreeMesh(scene, o.x, o.z, treeMat, trunkMat);
      else addRockMesh(scene, o.x, o.z, o.radius, rockMat);
      obstacles.push({ ...o });
    }
    return obstacles;
  }

  const rand = mulberry32(1337);

  for (let i = 0; i < 40; i++) {
    const angle = rand() * Math.PI * 2;
    const dist = 6 + rand() * (WORLD_RADIUS - 8);
    const x = Math.cos(angle) * dist;
    const z = Math.sin(angle) * dist;

    if (rand() > 0.4) {
      addTreeMesh(scene, x, z, treeMat, trunkMat);
      obstacles.push({ type: 'tree', x, z, radius: 0.5 });
    } else {
      const radius = 0.3 + rand() * 0.35;
      addRockMesh(scene, x, z, radius, rockMat);
      obstacles.push({ type: 'rock', x, z, radius });
    }
  }

  return obstacles;
}

export function clampToWorld(v: THREE.Vector3): void {
  const dist = Math.hypot(v.x, v.z);
  if (dist > WORLD_RADIUS - 1) {
    const scale = (WORLD_RADIUS - 1) / dist;
    v.x *= scale;
    v.z *= scale;
  }
}

function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
