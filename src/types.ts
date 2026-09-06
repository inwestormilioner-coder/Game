export type ClassId = 'knight' | 'archer' | 'mage' | 'druid' | 'assassin';

export interface ClassDef {
  id: ClassId;
  name: string;
  /** Base weapon damage multiplier at skill 0; melee/ranged flavor only, not balanced yet. */
  baseAttack: number;
  baseHp: number;
  hpPerLevel: number;
  baseResource: number;
  resourcePerLevel: number;
  resourceName: string;
  baseArmor: number;
  /** Carry capacity in kg (GDD Section 2.5). Knight > Archer > Assassin > Mage = Druid. */
  baseCapacity: number;
  capacityPerLevel: number;
}

// Base stat growth per level, from the GDD (Section 2.3). Pre-equipment/skill modifiers.
export const CLASSES: Record<ClassId, ClassDef> = {
  knight: {
    id: 'knight', name: 'Knight', baseAttack: 14,
    baseHp: 180, hpPerLevel: 19,
    baseResource: 40, resourcePerLevel: 3, resourceName: 'Fervor',
    baseArmor: 12,
    baseCapacity: 450, capacityPerLevel: 15,
  },
  archer: {
    id: 'archer', name: 'Archer', baseAttack: 12,
    baseHp: 140, hpPerLevel: 13,
    baseResource: 60, resourcePerLevel: 6, resourceName: 'Focus',
    baseArmor: 8,
    baseCapacity: 380, capacityPerLevel: 12,
  },
  mage: {
    id: 'mage', name: 'Mage', baseAttack: 16,
    baseHp: 90, hpPerLevel: 7,
    baseResource: 110, resourcePerLevel: 11, resourceName: 'Mana',
    baseArmor: 4,
    baseCapacity: 250, capacityPerLevel: 6,
  },
  druid: {
    id: 'druid', name: 'Druid', baseAttack: 9,
    baseHp: 100, hpPerLevel: 8,
    baseResource: 100, resourcePerLevel: 10, resourceName: 'Mana',
    baseArmor: 5,
    baseCapacity: 250, capacityPerLevel: 6,
  },
  assassin: {
    id: 'assassin', name: 'Assassin', baseAttack: 18,
    baseHp: 100, hpPerLevel: 8,
    baseResource: 70, resourcePerLevel: 6, resourceName: 'Momentum',
    baseArmor: 5,
    baseCapacity: 320, capacityPerLevel: 9,
  },
};

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

/** Successful actions needed to advance a skill from level S to S+1. */
export function actionsToAdvanceSkill(skillLevel: number, rate: SkillRate): number {
  return Math.ceil(6 * SKILL_RATE_MULTIPLIER[rate] * Math.pow(skillLevel, 1.7));
}

export type EquipSlot = 'weapon' | 'armor';

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
  };
}

/** Recomputes level-derived stats (call after a level-up). Keeps current hp/resource topped up. */
export function applyLevelStats(stats: Stats): void {
  const def = CLASSES[stats.classId];
  stats.maxHp = def.baseHp + (stats.level - 1) * def.hpPerLevel;
  stats.maxResource = def.baseResource + (stats.level - 1) * def.resourcePerLevel;
  stats.hp = stats.maxHp;
  stats.resource = stats.maxResource;
  stats.attack = def.baseAttack + Math.floor((stats.level - 1) * 1.5);
  stats.maxCapacity = def.baseCapacity + (stats.level - 1) * def.capacityPerLevel;
  stats.expToNext = expToNextLevel(stats.level);
}
