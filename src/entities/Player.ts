import * as THREE from 'three';
import {
  applyLevelStats,
  createInitialStats,
  speedRatingForLevel,
  type ClassId,
  type EquipSlot,
  type Stats,
} from '../types';
import { ITEMS } from '../data/items';

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

  update(dt: number, moveX: number, moveY: number): void {
    if (this.attackTimer > 0) this.attackTimer -= dt;

    const len = Math.hypot(moveX, moveY);
    if (len > 0.05) {
      const dx = moveX / len;
      const dz = moveY / len;
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

  /** Base attack (from level/class) plus the equipped weapon's bonus, if any. */
  get effectiveAttack(): number {
    const weaponId = this.stats.equipment.weapon;
    const bonus = weaponId ? (ITEMS[weaponId].equip?.attackBonus ?? 0) : 0;
    return this.stats.attack + bonus;
  }

  /** Base armor (from level/class) plus the equipped armor's bonus, if any. */
  get effectiveArmor(): number {
    const armorId = this.stats.equipment.armor;
    const bonus = armorId ? (ITEMS[armorId].equip?.armorBonus ?? 0) : 0;
    return this.stats.armor + bonus;
  }

  /** GDD Section 3: Mitigation = Armor / (Armor + 50) — asymptotic, never reaches 100%. */
  takeDamage(amount: number): void {
    const mitigation = this.effectiveArmor / (this.effectiveArmor + 50);
    const dealt = Math.round(amount * (1 - mitigation));
    this.stats.hp = Math.max(0, this.stats.hp - dealt);
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

  /** Total weight of backpack contents AND equipped gear — wearing something doesn't make it weightless. */
  get carriedWeight(): number {
    let total = 0;
    for (const [itemId, qty] of Object.entries(this.stats.inventory)) {
      total += ITEMS[itemId].weight * qty;
    }
    for (const itemId of Object.values(this.stats.equipment)) {
      if (itemId) total += ITEMS[itemId].weight;
    }
    return total;
  }

  canCarry(itemId: string, qty: number): boolean {
    return this.carriedWeight + ITEMS[itemId].weight * qty <= this.stats.maxCapacity;
  }

  /** Returns false (and adds nothing) if the extra weight would exceed carry capacity. */
  addItem(itemId: string, qty: number): boolean {
    if (!this.canCarry(itemId, qty)) return false;
    this.stats.inventory[itemId] = (this.stats.inventory[itemId] ?? 0) + qty;
    return true;
  }

  /** Moving gear from backpack to equipped slot doesn't change total carried weight, so this never fails on capacity. */
  equipItem(itemId: string): boolean {
    const def = ITEMS[itemId];
    if (!def.equip) return false;
    if ((this.stats.inventory[itemId] ?? 0) <= 0) return false;

    this.stats.inventory[itemId] -= 1;
    if (this.stats.inventory[itemId] <= 0) delete this.stats.inventory[itemId];

    const previous = this.stats.equipment[def.equip.slot];
    if (previous) this.stats.inventory[previous] = (this.stats.inventory[previous] ?? 0) + 1;

    this.stats.equipment[def.equip.slot] = itemId;
    return true;
  }

  unequipItem(slot: EquipSlot): void {
    const itemId = this.stats.equipment[slot];
    if (!itemId) return;
    delete this.stats.equipment[slot];
    this.stats.inventory[itemId] = (this.stats.inventory[itemId] ?? 0) + 1;
  }

  get isDead(): boolean {
    return this.stats.hp <= 0;
  }

  respawn(): void {
    this.stats.hp = this.stats.maxHp;
    this.mesh.position.set(0, 0, 0);
  }
}
