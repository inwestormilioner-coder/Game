import * as THREE from 'three';
import {
  applyLevelStats,
  createInitialStats,
  speedRatingForLevel,
  type ClassId,
  type Stats,
} from '../types';

// World units/sec at speed rating 100 (level 1, no gear/mount bonuses).
const BASE_MOVE_SPEED = 5.5;
const ATTACK_RANGE = 2.2;
const ATTACK_COOLDOWN = 0.55;

export class Player {
  readonly mesh: THREE.Group;
  readonly stats: Stats;

  private attackTimer = 0;
  facing = new THREE.Vector3(0, 0, 1);

  constructor(classId: ClassId = 'knight') {
    this.stats = createInitialStats(classId);
    this.mesh = new THREE.Group();

    const body = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.4, 0.9, 4, 8),
      new THREE.MeshStandardMaterial({ color: 0x3fa9f5 }),
    );
    body.position.y = 0.85;
    body.castShadow = true;

    const head = new THREE.Mesh(
      new THREE.SphereGeometry(0.28, 12, 12),
      new THREE.MeshStandardMaterial({ color: 0xffd9b3 }),
    );
    head.position.y = 1.55;
    head.castShadow = true;

    const weapon = new THREE.Mesh(
      new THREE.BoxGeometry(0.08, 0.9, 0.08),
      new THREE.MeshStandardMaterial({ color: 0xcccccc, metalness: 0.6, roughness: 0.3 }),
    );
    weapon.position.set(0.5, 0.9, 0);
    weapon.rotation.z = 0.3;

    this.mesh.add(body, head, weapon);
  }

  get position(): THREE.Vector3 {
    return this.mesh.position;
  }

  get canAttack(): boolean {
    return this.attackTimer <= 0;
  }

  /** Current move speed in world units/sec, from the GDD's movement-speed curve. */
  get moveSpeed(): number {
    return BASE_MOVE_SPEED * (speedRatingForLevel(this.stats.level) / 100);
  }

  /** cameraYaw rotates the joystick's input so "forward" always tracks the camera, not world axes. */
  update(dt: number, moveX: number, moveY: number, cameraYaw = 0): void {
    if (this.attackTimer > 0) this.attackTimer -= dt;

    const len = Math.hypot(moveX, moveY);
    if (len > 0.05) {
      const ix = moveX / len;
      const iy = moveY / len;
      const sin = Math.sin(cameraYaw);
      const cos = Math.cos(cameraYaw);
      const dx = ix * cos + iy * sin;
      const dz = iy * cos - ix * sin;
      const speed = this.moveSpeed;
      this.mesh.position.x += dx * speed * dt;
      this.mesh.position.z += dz * speed * dt;
      this.facing.set(dx, 0, dz);
      this.mesh.rotation.y = Math.atan2(dx, dz);
    }
  }

  /** Attempts an attack; returns true if it actually fired (i.e. off cooldown). */
  tryAttack(): boolean {
    if (!this.canAttack) return false;
    this.attackTimer = ATTACK_COOLDOWN;
    return true;
  }

  isInRange(target: THREE.Vector3): boolean {
    return this.position.distanceTo(target) <= ATTACK_RANGE;
  }

  takeDamage(amount: number): void {
    this.stats.hp = Math.max(0, this.stats.hp - amount);
  }

  gainExp(amount: number): boolean {
    let leveledUp = false;
    this.stats.exp += amount;
    while (this.stats.exp >= this.stats.expToNext) {
      this.stats.exp -= this.stats.expToNext;
      this.stats.level += 1;
      applyLevelStats(this.stats);
      leveledUp = true;
    }
    return leveledUp;
  }

  gainGold(amount: number): void {
    this.stats.gold += amount;
  }

  get isDead(): boolean {
    return this.stats.hp <= 0;
  }

  respawn(): void {
    this.stats.hp = this.stats.maxHp;
    this.mesh.position.set(0, 0, 0);
  }
}
