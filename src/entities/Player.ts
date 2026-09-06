import * as THREE from 'three';
import {
  actionsToAdvanceSkill,
  applyLevelStats,
  blockChance,
  CAPE_UNLOCK_LEVEL,
  CLASSES,
  createInitialStats,
  HP_REGEN_RATE,
  initialSkillLevel,
  PRIMARY_SKILL,
  REGEN_TICK_SECONDS,
  SATIETY_CAP_SECONDS,
  speedRatingForLevel,
  WARDCRAFT_RATE,
  type ClassId,
  type EquipSlot,
  type SkillId,
  type SkillRate,
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
  private regenAccumulator = 0;
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

  get primarySkillId(): SkillId {
    return PRIMARY_SKILL[this.stats.classId];
  }

  get primarySkillLevel(): number {
    return this.stats.skills[this.primarySkillId]?.level ?? initialSkillLevel(this.primarySkillId);
  }

  /**
   * GDD Section 3: `(WeaponBaseDamage + LevelBonus) × (1 + WeaponSkillLevel/100) × EquipmentModifiers`.
   * `stats.attack` already carries BaseDamage+LevelBonus (see applyLevelStats); the flat weapon-gear
   * bonus stands in for EquipmentModifiers until items get real multiplier affixes.
   */
  get effectiveAttack(): number {
    const weaponId = this.stats.equipment.weapon;
    const gearBonus = weaponId ? (ITEMS[weaponId].equip?.attackBonus ?? 0) : 0;
    const skillMultiplier = 1 + this.primarySkillLevel / 100;
    return Math.round((this.stats.attack + gearBonus) * skillMultiplier);
  }

  private trainSkill(skillId: SkillId, rate: SkillRate): { leveledUp: boolean; newLevel: number } {
    const current = this.stats.skills[skillId] ?? { level: initialSkillLevel(skillId), progress: 0 };
    current.progress += 1;

    let leveledUp = false;
    let needed = actionsToAdvanceSkill(current.level, rate);
    while (current.progress >= needed) {
      current.progress -= needed;
      current.level += 1;
      leveledUp = true;
      needed = actionsToAdvanceSkill(current.level, rate);
    }

    this.stats.skills[skillId] = current;
    return { leveledUp, newLevel: current.level };
  }

  /** Call on every successful hit/cast — trains the class's signature skill (GDD Section 5). */
  trainPrimarySkill(): { leveledUp: boolean; newLevel: number } {
    return this.trainSkill(this.primarySkillId, 'veryFast');
  }

  get wardcraftLevel(): number {
    return this.stats.skills.wardcraft?.level ?? initialSkillLevel('wardcraft');
  }

  /** 0 without a shield equipped — Wardcraft governs how good you are at blocking, not whether you can. */
  get blockChance(): number {
    return this.stats.equipment.shield ? blockChance(this.wardcraftLevel) : 0;
  }

  /** Base armor (from level/class) plus every equipped piece's armor bonus (all ten slots can carry one). */
  get effectiveArmor(): number {
    let bonus = 0;
    for (const itemId of Object.values(this.stats.equipment)) {
      if (itemId) bonus += ITEMS[itemId].equip?.armorBonus ?? 0;
    }
    return this.stats.armor + bonus;
  }

  /** Base resource pool plus bonuses from the amulet/reagent slots (Section 26). */
  get effectiveMaxResource(): number {
    let bonus = 0;
    for (const itemId of Object.values(this.stats.equipment)) {
      if (itemId) bonus += ITEMS[itemId].equip?.resourceBonus ?? 0;
    }
    return this.stats.maxResource + bonus;
  }

  /**
   * A successful block (shield + Wardcraft roll, Section 5) halves the incoming hit and trains
   * Wardcraft; armor mitigation (Section 3, Armor/(Armor+50)) always applies on top of that.
   */
  takeDamage(amount: number): { dealt: number; blocked: boolean; wardcraftLeveledUp: boolean; wardcraftLevel: number } {
    let incoming = amount;
    let blocked = false;
    let wardcraftLeveledUp = false;

    if (this.stats.equipment.shield && Math.random() < this.blockChance) {
      blocked = true;
      incoming = Math.round(incoming * 0.5);
      wardcraftLeveledUp = this.trainSkill('wardcraft', WARDCRAFT_RATE[this.stats.classId]).leveledUp;
    }

    const mitigation = this.effectiveArmor / (this.effectiveArmor + 50);
    const dealt = Math.round(incoming * (1 - mitigation));
    this.stats.hp = Math.max(0, this.stats.hp - dealt);
    return { dealt, blocked, wardcraftLeveledUp, wardcraftLevel: this.wardcraftLevel };
  }

  get isFed(): boolean {
    return this.stats.satietySeconds > 0;
  }

  get isPoisoned(): boolean {
    return this.stats.poisonTicksRemaining > 0;
  }

  /** Satiety drains every frame; poison and regen tick every REGEN_TICK_SECONDS (GDD Section 6). */
  updateSurvival(dt: number): void {
    if (this.stats.satietySeconds > 0) {
      this.stats.satietySeconds = Math.max(0, this.stats.satietySeconds - dt);
    }

    this.regenAccumulator += dt;
    while (this.regenAccumulator >= REGEN_TICK_SECONDS) {
      this.regenAccumulator -= REGEN_TICK_SECONDS;
      this.tickSurvival();
    }
  }

  private tickSurvival(): void {
    if (this.stats.poisonTicksRemaining > 0) {
      this.stats.hp = Math.max(0, this.stats.hp - this.stats.poisonDamagePerTick);
      this.stats.poisonTicksRemaining -= 1;
      if (this.stats.poisonTicksRemaining <= 0) this.stats.poisonDamagePerTick = 0;
    }

    if (!this.isFed) return;

    if (!this.isPoisoned && this.stats.hp < this.stats.maxHp) {
      const heal = Math.max(1, Math.round(this.stats.maxHp * HP_REGEN_RATE));
      this.stats.hp = Math.min(this.stats.maxHp, this.stats.hp + heal);
    }

    const baseRegen = CLASSES[this.stats.classId].baseRegen;
    if (baseRegen && this.stats.resource < this.effectiveMaxResource) {
      this.stats.resource = Math.min(this.effectiveMaxResource, this.stats.resource + baseRegen * REGEN_TICK_SECONDS);
    }
  }

  /** Returns false if there's none of that item to eat. Poisonous food always poisons — never a chance. */
  eat(itemId: string): boolean {
    const def = ITEMS[itemId];
    if (!def.food) return false;
    if ((this.stats.inventory[itemId] ?? 0) <= 0) return false;

    this.stats.inventory[itemId] -= 1;
    if (this.stats.inventory[itemId] <= 0) delete this.stats.inventory[itemId];

    this.stats.satietySeconds = Math.min(SATIETY_CAP_SECONDS, this.stats.satietySeconds + def.food.satietySeconds);

    if (def.food.poisonDamagePerTick && def.food.poisonTicks) {
      this.stats.poisonDamagePerTick = Math.max(this.stats.poisonDamagePerTick, def.food.poisonDamagePerTick);
      this.stats.poisonTicksRemaining += def.food.poisonTicks;
    }
    return true;
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
    if (def.equip.slot === 'cape' && this.stats.level < CAPE_UNLOCK_LEVEL) return false;
    if (def.equip.classes && !def.equip.classes.includes(this.stats.classId)) return false;

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
    this.stats.poisonTicksRemaining = 0;
    this.stats.poisonDamagePerTick = 0;
    this.mesh.position.set(0, 0, 0);
  }
}
