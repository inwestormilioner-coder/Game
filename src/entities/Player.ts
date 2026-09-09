import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import {
  actionsToAdvanceSkill,
  applyLevelStats,
  blockChance,
  CAPE_UNLOCK_LEVEL,
  CLASSES,
  createInitialStats,
  GATHER_RATE,
  HP_REGEN_RATE,
  initialSkillLevel,
  PRIMARY_SKILL,
  REGEN_TICK_SECONDS,
  SATIETY_CAP_SECONDS,
  speedRatingForLevel,
  WARDCRAFT_RATE,
  type ClassId,
  type EquipSlot,
  type GatherKind,
  type SkillId,
  type SkillRate,
  type Stats,
} from '../types';
import { ITEMS } from '../data/items';
import { ABILITIES, type AbilityDef } from '../data/abilities';
import { QUESTS } from '../data/quests';
import type { GatherNodeDef } from '../data/gathering';

// World units/sec at speed rating 100 (level 1, no gear/mount bonuses).
// Halved from 5.5 — real-device testing found movement (and the monsters'
// matching speeds in monsters.ts) way too fast relative to the new character art.
const BASE_MOVE_SPEED = 2.75;
export const ATTACK_RANGE = 2.2;
const ATTACK_COOLDOWN = 0.55;

// Real character models (Meshy.ai exports, merged with Mixamo-style animation clips —
// see docs/GDD.md Section 28). Only the Knight exists so far; other classes fall back to
// the placeholder primitive mesh below until their own models arrive.
const MODEL_PATHS: Partial<Record<ClassId, string>> = {
  knight: '/models/knight/knight.glb',
};

// The source clips run much longer than our actual combat timings — sped up on playback
// (via Action.timeScale) to land roughly within one attack cooldown / a quick damage flinch.
const ATTACK_ANIM_SECONDS = 0.7;
const HIT_ANIM_SECONDS = 0.35;
const LOOP_CROSSFADE_SECONDS = 0.2;

export type AbilityCastReason = 'cooldown' | 'resource';

export interface AbilityCastResult {
  ok: boolean;
  reason?: AbilityCastReason;
  /** effectiveAttack x damageMultiplier — only meaningful when the ability deals damage. */
  power: number;
}

export type GatherFailReason = 'cooldown' | 'skillTooLow' | 'noTool' | 'toolTooWeak' | 'noBait' | 'baitTooWeak' | 'full';

export interface GatherResult {
  ok: boolean;
  reason?: GatherFailReason;
  qty?: number;
  leveledUp?: boolean;
  newLevel?: number;
}

export class Player {
  readonly mesh: THREE.Group;
  readonly stats: Stats;

  private attackTimer = 0;
  private regenAccumulator = 0;
  private cooldowns: Record<string, number> = {};
  private attackBuffPercent = 0;
  private attackBuffRemaining = 0;
  private armorBuffPercent = 0;
  private armorBuffRemaining = 0;
  private moveSpeedBuffPercent = 0;
  private moveSpeedBuffRemaining = 0;
  private reflectPercentValue = 0;
  private reflectRemaining = 0;
  private attackSpeedBuffPercent = 0;
  private attackSpeedBuffRemaining = 0;
  private stealthOpacityValue = 1;
  private stealthRemaining = 0;
  facing = new THREE.Vector3(0, 0, 1);

  private readonly placeholder: THREE.Group;
  private mixer: THREE.AnimationMixer | null = null;
  private clips: Record<string, THREE.AnimationClip> = {};
  private currentAction: THREE.AnimationAction | null = null;
  private currentLoopName: string | null = null;
  private attackAnimTimer = 0;
  private hitAnimTimer = 0;
  private deathAnimTriggered = false;

  constructor(classId: ClassId = 'knight') {
    this.stats = createInitialStats(classId);
    this.mesh = new THREE.Group();

    // Placeholder primitive mesh — shown immediately, replaced once (if) the real model for
    // this class finishes loading. Classes without a model yet just keep this permanently.
    this.placeholder = new THREE.Group();

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

    this.placeholder.add(body, head, weapon);
    this.mesh.add(this.placeholder);

    const modelPath = MODEL_PATHS[classId];
    if (modelPath) this.loadModel(modelPath);
  }

  private loadModel(path: string): void {
    new GLTFLoader().load(
      path,
      (gltf) => {
        this.mesh.remove(this.placeholder);

        const model = gltf.scene;
        model.traverse((obj) => {
          if ((obj as THREE.Mesh).isMesh) obj.castShadow = true;
        });
        this.mesh.add(model);

        this.mixer = new THREE.AnimationMixer(model);
        for (const clip of gltf.animations) this.clips[clip.name] = clip;
        this.setLoop('Idle');
      },
      undefined,
      (err) => {
        console.error(`Failed to load player model "${path}" — keeping the placeholder mesh`, err);
      },
    );
  }

  /** Crossfades into a looping clip (Idle/Walk) — a no-op if it's already the active loop. */
  private setLoop(name: string): void {
    if (!this.mixer || this.currentLoopName === name) return;
    const clip = this.clips[name];
    if (!clip) return;

    const action = this.mixer.clipAction(clip);
    action.reset();
    action.setLoop(THREE.LoopRepeat, Infinity);
    action.clampWhenFinished = false;
    action.enabled = true;
    action.fadeIn(LOOP_CROSSFADE_SECONDS).play();

    if (this.currentAction && this.currentAction !== action) this.currentAction.fadeOut(LOOP_CROSSFADE_SECONDS);
    this.currentAction = action;
    this.currentLoopName = name;
  }

  /** Plays a clip once, sped up (or slowed) to land at targetSeconds, then holds its last frame. */
  private playOneShot(name: string, targetSeconds: number): void {
    if (!this.mixer) return;
    const clip = this.clips[name];
    if (!clip) return;

    const action = this.mixer.clipAction(clip);
    action.reset();
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
    action.timeScale = clip.duration / targetSeconds;
    action.enabled = true;
    action.fadeIn(0.1).play();

    if (this.currentAction && this.currentAction !== action) this.currentAction.fadeOut(0.1);
    this.currentAction = action;
    this.currentLoopName = null; // force setLoop to re-enter cleanly once the one-shot ends
  }

  /** Ticks the mixer and picks Idle/Walk/Attack/HitReaction/Death by priority — call once per frame. */
  private updateAnimation(dt: number, moving: boolean): void {
    if (!this.mixer) return;
    this.mixer.update(dt);

    if (this.isDead) {
      if (!this.deathAnimTriggered) {
        this.deathAnimTriggered = true;
        this.playOneShot('Death', 1.0);
      }
      return;
    }
    this.deathAnimTriggered = false;

    if (this.attackAnimTimer > 0) {
      this.attackAnimTimer -= dt;
      return;
    }
    if (this.hitAnimTimer > 0) {
      this.hitAnimTimer -= dt;
      return;
    }

    this.setLoop(moving ? 'Walk' : 'Idle');
  }

  get position(): THREE.Vector3 {
    return this.mesh.position;
  }

  get canAttack(): boolean {
    return this.attackTimer <= 0;
  }

  /** Seconds left before the next basic attack is allowed — test-only visibility into
   * tryAttack()'s cooldown, useful for verifying Archer's sprint haste actually shortens it. */
  get attackCooldownRemaining(): number {
    return this.attackTimer;
  }

  /** Current move speed in world units/sec, from the GDD's movement-speed curve. */
  get moveSpeed(): number {
    return BASE_MOVE_SPEED * (speedRatingForLevel(this.stats.level) / 100) * (1 + this.moveSpeedBuffPercent);
  }

  /** Fraction of incoming (post-mitigation) damage reflected back at the attacker while a
   * sprint barrier (Knight) is active — 0 otherwise. */
  get reflectPercent(): number {
    return this.reflectPercentValue;
  }

  /** 1 = fully visible, down to e.g. 0.02 while a stealth sprint (Assassin) is active. */
  get stealthOpacity(): number {
    return this.stealthOpacityValue;
  }

  get isStealthed(): boolean {
    return this.stealthOpacityValue < 1;
  }

  update(dt: number, moveX: number, moveY: number): void {
    if (this.attackTimer > 0) this.attackTimer -= dt;

    const len = Math.hypot(moveX, moveY);
    const moving = len > 0.05;
    if (moving) {
      // The fixed camera (Game.ts CAMERA_OFFSET) faces world +Z with its on-screen "right"
      // pointing toward world -X — both joystick axes are negated here so pushing the stick
      // right/up actually moves the character right/away on screen, not the mirror of that.
      const dx = -moveX / len;
      const dz = -moveY / len;
      const speed = this.moveSpeed;
      this.mesh.position.x += dx * speed * dt;
      this.mesh.position.z += dz * speed * dt;
      this.facing.set(dx, 0, dz);
      this.mesh.rotation.y = Math.atan2(dx, dz);
    }

    this.updateAnimation(dt, moving);
  }

  /** Attempts an attack; returns true if it actually fired (i.e. off cooldown). */
  tryAttack(): boolean {
    if (!this.canAttack) return false;
    this.attackTimer = ATTACK_COOLDOWN * (1 - this.attackSpeedBuffPercent);
    this.attackAnimTimer = ATTACK_ANIM_SECONDS;
    this.playOneShot('Attack', ATTACK_ANIM_SECONDS);
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
    const buffMultiplier = 1 + this.attackBuffPercent;
    return Math.round((this.stats.attack + gearBonus) * skillMultiplier * buffMultiplier);
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

  /** Base armor (from level/class) plus gear bonuses plus any active armor buff (Fortify, Arcane Shield, ...). */
  get effectiveArmor(): number {
    let bonus = 0;
    for (const itemId of Object.values(this.stats.equipment)) {
      if (itemId) bonus += ITEMS[itemId].equip?.armorBonus ?? 0;
    }
    return Math.round((this.stats.armor + bonus) * (1 + this.armorBuffPercent));
  }

  /** Base resource pool plus bonuses from the amulet/reagent slots (Section 26). */
  get effectiveMaxResource(): number {
    let bonus = 0;
    for (const itemId of Object.values(this.stats.equipment)) {
      if (itemId) bonus += ITEMS[itemId].equip?.resourceBonus ?? 0;
    }
    return this.stats.maxResource + bonus;
  }

  /** Ticks ability cooldowns and buff durations — call once per frame (GDD Section 8/10). */
  updateAbilities(dt: number): void {
    for (const id of Object.keys(this.cooldowns)) {
      this.cooldowns[id] = Math.max(0, this.cooldowns[id] - dt);
    }
    if (this.attackBuffRemaining > 0) {
      this.attackBuffRemaining -= dt;
      if (this.attackBuffRemaining <= 0) this.attackBuffPercent = 0;
    }
    if (this.armorBuffRemaining > 0) {
      this.armorBuffRemaining -= dt;
      if (this.armorBuffRemaining <= 0) this.armorBuffPercent = 0;
    }
    if (this.moveSpeedBuffRemaining > 0) {
      this.moveSpeedBuffRemaining -= dt;
      if (this.moveSpeedBuffRemaining <= 0) this.moveSpeedBuffPercent = 0;
    }
    if (this.reflectRemaining > 0) {
      this.reflectRemaining -= dt;
      if (this.reflectRemaining <= 0) this.reflectPercentValue = 0;
    }
    if (this.attackSpeedBuffRemaining > 0) {
      this.attackSpeedBuffRemaining -= dt;
      if (this.attackSpeedBuffRemaining <= 0) this.attackSpeedBuffPercent = 0;
    }
    if (this.stealthRemaining > 0) {
      this.stealthRemaining -= dt;
      if (this.stealthRemaining <= 0) this.stealthOpacityValue = 1;
    }
    this.applyStealthVisual();
  }

  private applyStealthVisual(): void {
    this.mesh.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (!mesh.isMesh) return;
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const mat of materials) {
        const m = mat as THREE.Material & { opacity: number; transparent: boolean };
        m.transparent = this.stealthOpacityValue < 1;
        m.opacity = this.stealthOpacityValue;
      }
    });
  }

  getCooldownRemaining(abilityId: string): number {
    return this.cooldowns[abilityId] ?? 0;
  }

  /**
   * Spends resource/starts cooldown and applies every self-only effect field (heal, buffs, dash)
   * immediately. Anything that needs to touch a monster (damage/aoe/stun/slow) is left for the
   * caller (Game.ts) to apply, using the returned `power` for damage-scaled effects.
   */
  tryUseAbility(abilityId: string): AbilityCastResult {
    const def: AbilityDef | undefined = ABILITIES[abilityId];
    if (!def) return { ok: false, power: 0 };
    if (this.getCooldownRemaining(abilityId) > 0) return { ok: false, reason: 'cooldown', power: 0 };
    if (this.stats.resource < def.resourceCost) return { ok: false, reason: 'resource', power: 0 };

    this.stats.resource -= def.resourceCost;
    this.cooldowns[abilityId] = def.cooldown;
    const { effect } = def;
    const power = effect.damageMultiplier ? Math.round(this.effectiveAttack * effect.damageMultiplier) : 0;

    if (effect.healPercent) {
      this.stats.hp = Math.min(this.stats.maxHp, this.stats.hp + Math.round(this.stats.maxHp * effect.healPercent));
    }
    if (effect.buffAttackPercent && effect.buffDuration) {
      this.attackBuffPercent = effect.buffAttackPercent;
      this.attackBuffRemaining = effect.buffDuration;
    }
    if (effect.buffArmorPercent && effect.buffDuration) {
      this.armorBuffPercent = effect.buffArmorPercent;
      this.armorBuffRemaining = effect.buffDuration;
    }
    if (effect.buffMoveSpeedPercent && effect.buffDuration) {
      this.moveSpeedBuffPercent = effect.buffMoveSpeedPercent;
      this.moveSpeedBuffRemaining = effect.buffDuration;
    }
    if (effect.reflectPercent && effect.buffDuration) {
      this.reflectPercentValue = effect.reflectPercent;
      this.reflectRemaining = effect.buffDuration;
    }
    if (effect.buffAttackSpeedPercent && effect.buffDuration) {
      this.attackSpeedBuffPercent = effect.buffAttackSpeedPercent;
      this.attackSpeedBuffRemaining = effect.buffDuration;
    }
    if (effect.stealthOpacity && effect.buffDuration) {
      this.stealthOpacityValue = effect.stealthOpacity;
      this.stealthRemaining = effect.buffDuration;
    }
    if (effect.dashDistance) {
      const dir = effect.dashDirection === 'away' ? this.facing.clone().negate() : this.facing.clone();
      this.mesh.position.addScaledVector(dir, effect.dashDistance);
    }

    return { ok: true, power };
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

    if (dealt > 0 && this.stats.hp > 0) {
      this.hitAnimTimer = HIT_ANIM_SECONDS;
      this.playOneShot('HitReaction', HIT_ANIM_SECONDS);
    }

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

  /** Moves an item from the backpack into this city's Depot (GDD Section 18) — no capacity check, it's storage. */
  depositItem(itemId: string, qty = 1): boolean {
    if ((this.stats.inventory[itemId] ?? 0) < qty) return false;
    this.stats.inventory[itemId] -= qty;
    if (this.stats.inventory[itemId] <= 0) delete this.stats.inventory[itemId];
    this.stats.depot[itemId] = (this.stats.depot[itemId] ?? 0) + qty;
    return true;
  }

  /** Moves an item from the Depot back into the backpack — gated on carry capacity like any pickup. */
  withdrawItem(itemId: string, qty = 1): boolean {
    if ((this.stats.depot[itemId] ?? 0) < qty) return false;
    if (!this.canCarry(itemId, qty)) return false;
    this.stats.depot[itemId] -= qty;
    if (this.stats.depot[itemId] <= 0) delete this.stats.depot[itemId];
    this.stats.inventory[itemId] = (this.stats.inventory[itemId] ?? 0) + qty;
    return true;
  }

  questState(questId: string) {
    return this.stats.quests[questId];
  }

  /** Accepts a quest from its giver — a no-op if already known (GDD Section 15: no re-offering). */
  startQuest(questId: string): boolean {
    if (this.stats.quests[questId]) return false;
    this.stats.quests[questId] = { status: 'active', progress: 0 };
    return true;
  }

  /** Call on every monster kill — advances any of the player's active quests targeting that
   * monster type. Returns the ids of quests that just became ready to turn in. */
  registerMonsterKill(monsterId: string): string[] {
    const readyNow: string[] = [];
    for (const [questId, def] of Object.entries(QUESTS)) {
      if (def.targetMonsterId !== monsterId) continue;
      const state = this.stats.quests[questId];
      if (!state || state.status !== 'active') continue;
      state.progress += 1;
      if (state.progress >= def.targetCount) {
        state.status = 'readyToTurnIn';
        readyNow.push(questId);
      }
    }
    return readyNow;
  }

  /** Applies rewards and marks the quest complete. False if it wasn't actually ready. */
  turnInQuest(questId: string): { ok: boolean; leveledUp: boolean } {
    const state = this.stats.quests[questId];
    const def = QUESTS[questId];
    if (!state || !def || state.status !== 'readyToTurnIn') return { ok: false, leveledUp: false };

    state.status = 'completed';
    const leveledUp = this.gainExp(def.rewardXp);
    this.gainGold(def.rewardGold);
    if (def.rewardItemId) this.addItem(def.rewardItemId, 1);
    return { ok: true, leveledUp };
  }

  skillLevel(skillId: SkillId): number {
    return this.stats.skills[skillId]?.level ?? initialSkillLevel(skillId);
  }

  /** Tier of the gathering tool currently equipped in the weapon slot for this kind, or 0 if
   * none/wrong kind is equipped. Tools share the weapon slot with combat weapons — equipping a
   * pickaxe to mine means unequipping whatever sword/bow was there, exactly like swapping gear
   * (gathering professions: no separate proximity prompt, just equip the tool and tap ATAK). */
  bestToolTier(kind: GatherKind): number {
    const weaponId = this.stats.equipment.weapon;
    if (!weaponId) return 0;
    const tool = ITEMS[weaponId].tool;
    return tool && tool.kind === kind ? tool.tier : 0;
  }

  private bestBait(): { itemId: string; tier: number } | null {
    let best: { itemId: string; tier: number } | null = null;
    for (const [itemId, qty] of Object.entries(this.stats.inventory)) {
      if (qty <= 0) continue;
      const bait = ITEMS[itemId].bait;
      if (bait && (!best || bait.tier > best.tier)) best = { itemId, tier: bait.tier };
    }
    return best;
  }

  bestBaitTier(): number {
    return this.bestBait()?.tier ?? 0;
  }

  getGatherCooldownRemaining(kind: GatherKind): number {
    return this.getCooldownRemaining(`gather:${kind}`);
  }

  trainGatherSkill(skillId: GatherKind): { leveledUp: boolean; newLevel: number } {
    return this.trainSkill(skillId, GATHER_RATE[skillId]);
  }

  /**
   * Attempts to gather from a node. Skill level gates whether the node can be attempted at all
   * (a "harder mine" needs a higher Mining level); tool tier (and bait tier, fishing only) gates
   * whether the attempt succeeds once allowed — never the yield's randomness, gathering itself is
   * deterministic (RNG stays reserved for monster loot, Section 12). A higher skill level shortens
   * the post-gather cooldown, which is what makes leveling up "faster gathering" in practice.
   */
  tryGather(node: GatherNodeDef): GatherResult {
    if (this.getGatherCooldownRemaining(node.kind) > 0) return { ok: false, reason: 'cooldown' };
    if (this.skillLevel(node.kind) < node.requiredSkillLevel) return { ok: false, reason: 'skillTooLow' };

    const toolTier = this.bestToolTier(node.kind);
    if (toolTier <= 0) return { ok: false, reason: 'noTool' };
    if (toolTier < node.tier) return { ok: false, reason: 'toolTooWeak' };

    if (node.kind === 'fishing') {
      const baitTier = this.bestBaitTier();
      if (baitTier <= 0) return { ok: false, reason: 'noBait' };
      if (baitTier < node.tier) return { ok: false, reason: 'baitTooWeak' };
    }

    const qty = node.yieldQtyMin + Math.floor(Math.random() * (node.yieldQtyMax - node.yieldQtyMin + 1));
    if (!this.canCarry(node.yieldItemId, qty)) return { ok: false, reason: 'full' };

    if (node.kind === 'fishing') {
      const bait = this.bestBait()!;
      this.stats.inventory[bait.itemId] -= 1;
      if (this.stats.inventory[bait.itemId] <= 0) delete this.stats.inventory[bait.itemId];
    }
    this.addItem(node.yieldItemId, qty);

    const level = this.skillLevel(node.kind);
    this.cooldowns[`gather:${node.kind}`] = Math.max(0.6, node.baseGatherSeconds / (1 + level / 100));

    const skillResult = this.trainGatherSkill(node.kind);
    return { ok: true, qty, leveledUp: skillResult.leveledUp, newLevel: skillResult.newLevel };
  }

  get isDead(): boolean {
    return this.stats.hp <= 0;
  }

  respawn(): void {
    this.stats.hp = this.stats.maxHp;
    this.stats.poisonTicksRemaining = 0;
    this.stats.poisonDamagePerTick = 0;
    this.mesh.position.set(0, 0, 0);
    this.deathAnimTriggered = false;
    this.attackAnimTimer = 0;
    this.hitAnimTimer = 0;
    this.currentLoopName = null;
    this.setLoop('Idle');
  }
}
