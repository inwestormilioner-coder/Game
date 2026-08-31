import * as THREE from 'three';
import { WORLD_RADIUS } from '../world/World';

const WANDER_SPEED = 1.2;
const AGGRO_RANGE = 3.2;
const ATTACK_RANGE = 1.6;
const ATTACK_COOLDOWN = 1.1;
const RESPAWN_DELAY = 6;

export interface MonsterDrop {
  exp: number;
  gold: number;
}

export class Monster {
  readonly mesh: THREE.Mesh;
  hp = 30;
  readonly maxHp = 30;
  readonly attack = 6;
  readonly drop: MonsterDrop = { exp: 18, gold: 5 };

  alive = true;
  private respawnTimer = 0;
  private wanderTarget = new THREE.Vector3();
  private wanderTimer = 0;
  private attackTimer = 0;
  private readonly homePosition: THREE.Vector3;

  constructor(spawnPosition: THREE.Vector3) {
    this.homePosition = spawnPosition.clone();
    this.mesh = new THREE.Mesh(
      new THREE.SphereGeometry(0.5, 12, 12),
      new THREE.MeshStandardMaterial({ color: 0x5fd35f, roughness: 0.4, transparent: true }),
    );
    this.mesh.position.copy(spawnPosition);
    this.mesh.position.y = 0.5;
    this.mesh.castShadow = true;
    this.pickNewWanderTarget();
  }

  private pickNewWanderTarget(): void {
    const angle = Math.random() * Math.PI * 2;
    const dist = Math.random() * 3;
    this.wanderTarget
      .set(this.homePosition.x + Math.cos(angle) * dist, 0.5, this.homePosition.z + Math.sin(angle) * dist)
      .clampLength(0, WORLD_RADIUS - 1);
    this.wanderTimer = 2 + Math.random() * 2;
  }

  /** Returns damage dealt to the player this frame, if any. */
  update(dt: number, playerPosition: THREE.Vector3): number {
    if (!this.alive) {
      this.respawnTimer -= dt;
      if (this.respawnTimer <= 0) this.respawn();
      return 0;
    }

    if (this.attackTimer > 0) this.attackTimer -= dt;

    const distToPlayer = this.mesh.position.distanceTo(playerPosition);

    if (distToPlayer <= AGGRO_RANGE) {
      const dir = new THREE.Vector3().subVectors(playerPosition, this.mesh.position);
      dir.y = 0;
      if (distToPlayer > ATTACK_RANGE) {
        dir.normalize();
        this.mesh.position.addScaledVector(dir, WANDER_SPEED * 1.4 * dt);
      } else if (this.attackTimer <= 0) {
        this.attackTimer = ATTACK_COOLDOWN;
        return this.attack;
      }
      return 0;
    }

    this.wanderTimer -= dt;
    if (this.wanderTimer <= 0) this.pickNewWanderTarget();
    const dir = new THREE.Vector3().subVectors(this.wanderTarget, this.mesh.position);
    dir.y = 0;
    if (dir.length() > 0.1) {
      dir.normalize();
      this.mesh.position.addScaledVector(dir, WANDER_SPEED * dt);
    }
    return 0;
  }

  takeDamage(amount: number): void {
    if (!this.alive) return;
    this.hp = Math.max(0, this.hp - amount);
    if (this.hp <= 0) this.die();
  }

  private die(): void {
    this.alive = false;
    this.respawnTimer = RESPAWN_DELAY;
    this.mesh.visible = false;
  }

  private respawn(): void {
    this.alive = true;
    this.hp = this.maxHp;
    this.mesh.visible = true;
    this.mesh.position.copy(this.homePosition);
    this.mesh.position.y = 0.5;
    this.pickNewWanderTarget();
  }
}
