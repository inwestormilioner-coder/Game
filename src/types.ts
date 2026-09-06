export type ClassId = 'knight' | 'archer' | 'mage' | 'druid' | 'assassin';

export interface ClassDef {
  id: ClassId;
  name: string;
  /** Base weapon damage multiplier at skill 0; melee/ranged flavor only, not balanced yet. */
  baseAttack: number;
  /** GDD Section 3 LevelBonus rate — how much this class's own attack (physical
   * or magical) grows per level, flat, never multiplicative. Assassin > Mage/
   * Archer > Druid > Knight, since Knight's per-level growth goes into Armor instead. */
  attackPerLevel: number;
  baseHp: number;
  hpPerLevel: number;
  baseResource: number;
  resourcePerLevel: number;
  resourceName: string;
  baseArmor: number;
  /** Mirrors the qualitative "Physical mitigation growth" column in Section 2.3:
   * Knight (High) > Archer (Medium) > Druid = Assassin (Low) > Mage (Very Low). */
  armorPerLevel: number;
  /** Carry capacity in kg (GDD Section 2.5). Knight > Archer > Assassin > Mage = Druid. */
  baseCapacity: number;
  capacityPerLevel: number;
  /** Passive resource regen/sec while Fed (Section 6). Absent for Knight/Assassin — Fervor
   * and Momentum are combat-driven only, so there's no passive regen for hunger to gate. */
  baseRegen?: number;
}

// Base stat growth per level, from the GDD (Section 2.3). Pre-equipment/skill modifiers.
export const CLASSES: Record<ClassId, ClassDef> = {
  knight: {
    id: 'knight', name: 'Knight', baseAttack: 14, attackPerLevel: 0.2,
    baseHp: 180, hpPerLevel: 19,
    baseResource: 40, resourcePerLevel: 3, resourceName: 'Fervor',
    baseArmor: 12, armorPerLevel: 0.6,
    baseCapacity: 450, capacityPerLevel: 15,
  },
  archer: {
    id: 'archer', name: 'Archer', baseAttack: 12, attackPerLevel: 0.4,
    baseHp: 140, hpPerLevel: 13,
    baseResource: 60, resourcePerLevel: 6, resourceName: 'Focus',
    baseArmor: 8, armorPerLevel: 0.3,
    baseCapacity: 380, capacityPerLevel: 12,
    baseRegen: 1.5,
  },
  mage: {
    id: 'mage', name: 'Mage', baseAttack: 16, attackPerLevel: 0.5,
    baseHp: 90, hpPerLevel: 7,
    baseResource: 110, resourcePerLevel: 11, resourceName: 'Mana',
    baseArmor: 4, armorPerLevel: 0.05,
    baseCapacity: 250, capacityPerLevel: 6,
    baseRegen: 1.2,
  },
  druid: {
    id: 'druid', name: 'Druid', baseAttack: 9, attackPerLevel: 0.25,
    baseHp: 100, hpPerLevel: 8,
    baseResource: 100, resourcePerLevel: 10, resourceName: 'Mana',
    baseArmor: 5, armorPerLevel: 0.15,
    baseCapacity: 250, capacityPerLevel: 6,
    baseRegen: 1.2,
  },
  assassin: {
    id: 'assassin', name: 'Assassin', baseAttack: 18, attackPerLevel: 0.6,
    baseHp: 100, hpPerLevel: 8,
    baseResource: 70, resourcePerLevel: 6, resourceName: 'Momentum',
    baseArmor: 5, armorPerLevel: 0.15,
    baseCapacity: 320, capacityPerLevel: 9,
  },
};

// ---- Satiety, regen & poison (GDD Section 6) ----
export const SATIETY_CAP_SECONDS = 60 * 60;
export const REGEN_TICK_SECONDS = 2;
export const HP_REGEN_RATE = 0.0025; // fraction of MaxHP healed per tick while Fed

// ---- Experience curve (GDD Section 4) ----
// TotalXP(L) = floor(5 * L^3.5); level 50 lands at ~4.4M, ~1 month of serious play.
export function totalXpForLevel(level: number): number {
  return Math.floor(5 * Math.pow(level, 3.5));
}

export function expToNextLevel(level: number): number {
  return totalXpForLevel(level + 1) - totalXpForLevel(level);
}

// ---- Movement speed (GDD Section 7) ----
// A "speed rating" of 100 = level-1 base walking speed, asymptotic toward 250 as level -> infinity.
const SPEED_BASE = 100;
const SPEED_CAP = 150;
const SPEED_DECAY = 120;

export function speedRatingForLevel(level: number): number {
  return SPEED_BASE + SPEED_CAP * (1 - Math.exp(-level / SPEED_DECAY));
}

// ---- Skill progression (GDD Section 5) ----
export type SkillRate = 'veryFast' | 'fast' | 'medium' | 'slow' | 'verySlow';

export const SKILL_RATE_MULTIPLIER: Record<SkillRate, number> = {
  veryFast: 0.6,
  fast: 0.85,
  medium: 1.2,
  slow: 1.8,
  verySlow: 3.0,
};

/** Successful actions needed to advance a skill from level S to S+1. Floored at 1 so the
 * S=0 case (Arcane Level's starting point) can't produce a free/zero-cost level-up. */
export function actionsToAdvanceSkill(skillLevel: number, rate: SkillRate): number {
  return Math.max(1, Math.ceil(6 * SKILL_RATE_MULTIPLIER[rate] * Math.pow(skillLevel, 1.7)));
}

// Every class's signature weapon skill (GDD Section 1/5) — the one this MVP
// trains via the basic attack, always at the VERY FAST rate for its own class.
// Off-class skills (a Knight's Distance, Wardcraft for everyone, etc.) are a
// later pass once there's more than one attack action to train them with.
export type SkillId = 'bladeFighting' | 'marksmanship' | 'talonFighting' | 'arcaneLevel' | 'wardcraft';

export const SKILL_NAMES: Record<SkillId, string> = {
  bladeFighting: 'Blade Fighting',
  marksmanship: 'Marksmanship',
  talonFighting: 'Talon Fighting',
  arcaneLevel: 'Arcane Level',
  wardcraft: 'Wardcraft',
};

export const PRIMARY_SKILL: Record<ClassId, SkillId> = {
  knight: 'bladeFighting',
  archer: 'marksmanship',
  mage: 'arcaneLevel',
  druid: 'arcaneLevel',
  assassin: 'talonFighting',
};

/** Weapon skills start at 10, Arcane Level starts at 0 (GDD Section 5). */
export function initialSkillLevel(skillId: SkillId): number {
  return skillId === 'arcaneLevel' ? 0 : 10;
}

export interface SkillProgress {
  level: number;
  /** Successful actions banked toward the next level. */
  progress: number;
}

// GDD Section 26: ten real slots, no shared "accessory" catch-all.
export type EquipSlot =
  | 'helmet'
  | 'armor'
  | 'legs'
  | 'boots'
  | 'gloves'
  | 'weapon'
  | 'shield'
  | 'ammo'
  | 'amulet'
  | 'cape';

/** The cape slot itself doesn't appear on the sheet before this — not just its items. */
export const CAPE_UNLOCK_LEVEL = 10;

export interface Stats {
  classId: ClassId;
  level: number;
  hp: number;
  maxHp: number;
  resource: number;
  maxResource: number;
  resourceName: string;
  exp: number;
  expToNext: number;
  /** Base values from level/class only — see Player.effectiveAttack/effectiveArmor for the gear-adjusted ones. */
  attack: number;
  armor: number;
  gold: number;
  maxCapacity: number;
  /** itemId -> quantity carried in the backpack (not equipped). */
  inventory: Record<string, number>;
  equipment: Partial<Record<EquipSlot, string>>;
  /** Seconds of "Fed" remaining — HP/Mana/Focus only regen while this is above 0 (Section 6). */
  satietySeconds: number;
  poisonTicksRemaining: number;
  poisonDamagePerTick: number;
  skills: Partial<Record<SkillId, SkillProgress>>;
}

export function createInitialStats(classId: ClassId = 'knight'): Stats {
  const def = CLASSES[classId];
  return {
    classId,
    level: 1,
    hp: def.baseHp,
    maxHp: def.baseHp,
    resource: def.baseResource,
    maxResource: def.baseResource,
    resourceName: def.resourceName,
    exp: 0,
    expToNext: expToNextLevel(1),
    attack: def.baseAttack,
    armor: def.baseArmor,
    gold: 0,
    maxCapacity: def.baseCapacity,
    inventory: {},
    equipment: {},
    satietySeconds: 0,
    poisonTicksRemaining: 0,
    poisonDamagePerTick: 0,
    skills: {
      [PRIMARY_SKILL[classId]]: { level: initialSkillLevel(PRIMARY_SKILL[classId]), progress: 0 },
    },
  };
}

// GDD Section 3: LevelBonus = floor((Level-1) * ClassDef.attackPerLevel) — small
// and flat, never multiplicative, so level alone can't collapse time-to-kill.
// Real damage growth still has to come from WeaponSkillLevel/ArcaneLevel + gear.
export function levelAttackBonus(level: number, classId: ClassId): number {
  return Math.floor((level - 1) * CLASSES[classId].attackPerLevel);
}

export function levelArmorBonus(level: number, classId: ClassId): number {
  return Math.floor((level - 1) * CLASSES[classId].armorPerLevel);
}

/** Recomputes level-derived stats (call after a level-up). Keeps current hp/resource topped up. */
export function applyLevelStats(stats: Stats): void {
  const def = CLASSES[stats.classId];
  stats.maxHp = def.baseHp + (stats.level - 1) * def.hpPerLevel;
  stats.maxResource = def.baseResource + (stats.level - 1) * def.resourcePerLevel;
  stats.hp = stats.maxHp;
  stats.resource = stats.maxResource;
  stats.attack = def.baseAttack + levelAttackBonus(stats.level, stats.classId);
  stats.armor = def.baseArmor + levelArmorBonus(stats.level, stats.classId);
  stats.maxCapacity = def.baseCapacity + (stats.level - 1) * def.capacityPerLevel;
  stats.expToNext = expToNextLevel(stats.level);
}
