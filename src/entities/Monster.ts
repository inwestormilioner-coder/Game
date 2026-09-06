import * as THREE from 'three';
import { WORLD_RADIUS } from '../world/World';
import { rollLoot, type LootDrop } from '../systems/loot';
import type { MonsterDef } from '../data/monsters';

export interface MonsterResult {
  exp: number;
  gold: number;
  items: LootDrop[];
}

export class Monster {
  readonly mesh: THREE.Mesh;
  readonly def: MonsterDef;
  hp: number;
  alive = true;

  private respawnTimer = 0;
  private wanderTarget = new THREE.Vector3();
  private wanderTimer = 0;
  private attackTimer = 0;
  private stunRemaining = 0;
  private slowPercent = 0;
  private slowRemaining = 0;
  private readonly homePosition: THREE.Vector3;

  constructor(def: MonsterDef, spawnPosition: THREE.Vector3) {
    this.def = def;
    this.hp = def.hp;
    this.homePosition = spawnPosition.clone();
    this.mesh = new THREE.Mesh(
      new THREE.SphereGeometry(def.radius, 12, 12),
      new THREE.MeshStandardMaterial({ color: def.color, roughness: 0.5, transparent: true }),
    );
    this.mesh.position.copy(spawnPosition);
    this.mesh.position.y = def.radius;
    this.mesh.castShadow = true;
    this.pickNewWanderTarget();
  }

  get maxHp(): number {
    return this.def.hp;
  }

  private pickNewWanderTarget(): void {
    const angle = Math.random() * Math.PI * 2;
    const dist = Math.random() * 3;
    this.wanderTarget
      .set(
        this.homePosition.x + Math.cos(angle) * dist,
        this.def.radius,
        this.homePosition.z + Math.sin(angle) * dist,
      )
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

    if (this.slowRemaining > 0) {
      this.slowRemaining -= dt;
      if (this.slowRemaining <= 0) this.slowPercent = 0;
    }

    if (this.stunRemaining > 0) {
      this.stunRemaining -= dt;
      return 0; // frozen — no movement, no attacks, while stunned
    }

    const moveSpeed = this.def.moveSpeed * (1 - this.slowPercent);
    const distToPlayer = this.mesh.position.distanceTo(playerPosition);
    const inAggro = distToPlayer <= this.def.aggroRange;

    if (this.def.behavior === 'passive') {
      if (inAggro) {
        this.fleeFrom(playerPosition, dt, moveSpeed);
        return 0;
      }
    } else if (inAggro) {
      if (distToPlayer > this.def.attackRange) {
        this.stepToward(playerPosition, moveSpeed, dt);
      } else if (this.attackTimer <= 0) {
        this.attackTimer = this.def.attackCooldown;
        return this.def.damageMin + Math.floor(Math.random() * (this.def.damageMax - this.def.damageMin + 1));
      }
      return 0;
    }

    this.wanderTimer -= dt;
    if (this.wanderTimer <= 0) this.pickNewWanderTarget();
    this.stepToward(this.wanderTarget, moveSpeed, dt);
    return 0;
  }

  /** Stacks/refreshes to the stronger of the current and incoming effect (GDD Section 8 abilities). */
  applyStun(duration: number): void {
    this.stunRemaining = Math.max(this.stunRemaining, duration);
  }

  applySlow(percent: number, duration: number): void {
    this.slowPercent = Math.max(this.slowPercent, percent);
    this.slowRemaining = Math.max(this.slowRemaining, duration);
  }

  private stepToward(target: THREE.Vector3, speed: number, dt: number): void {
    const dir = new THREE.Vector3().subVectors(target, this.mesh.position);
    dir.y = 0;
    if (dir.length() <= 0.1) return;
    dir.normalize();
    this.mesh.position.addScaledVector(dir, speed * dt);
    this.mesh.position.y = this.def.radius;
  }

  private fleeFrom(threat: THREE.Vector3, dt: number, speed: number): void {
    const away = new THREE.Vector3().subVectors(this.mesh.position, threat);
    away.y = 0;
    if (away.lengthSq() <= 0.0001) return;
    away.normalize();
    this.mesh.position.addScaledVector(away, speed * 1.3 * dt);
    this.mesh.position.y = this.def.radius;
  }

  takeDamage(amount: number): void {
    if (!this.alive) return;
    this.hp = Math.max(0, this.hp - amount);
    if (this.hp <= 0) this.die();
  }

  /** Call once, right after a kill — rolls gold/loot, so don't call it twice for one death. */
  rollResult(): MonsterResult {
    const gold = this.def.goldMin + Math.floor(Math.random() * (this.def.goldMax - this.def.goldMin + 1));
    return { exp: this.def.xp, gold, items: rollLoot(this.def.lootTable) };
  }

  private die(): void {
    this.alive = false;
    this.respawnTimer = this.def.respawnDelay;
    this.stunRemaining = 0;
    this.slowPercent = 0;
    this.slowRemaining = 0;
    this.mesh.visible = false;
  }

  private respawn(): void {
    this.alive = true;
    this.hp = this.def.hp;
    this.mesh.visible = true;
    this.mesh.position.copy(this.homePosition);
    this.mesh.position.y = this.def.radius;
    this.pickNewWanderTarget();
  }
}
