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
}

// Base stat growth per level, from the GDD (Section 2.3). Pre-equipment/skill modifiers.
export const CLASSES: Record<ClassId, ClassDef> = {
  knight: {
    id: 'knight', name: 'Knight', baseAttack: 14,
    baseHp: 180, hpPerLevel: 19,
    baseResource: 40, resourcePerLevel: 3, resourceName: 'Fervor',
    baseArmor: 12,
  },
  archer: {
    id: 'archer', name: 'Archer', baseAttack: 12,
    baseHp: 140, hpPerLevel: 13,
    baseResource: 60, resourcePerLevel: 6, resourceName: 'Focus',
    baseArmor: 8,
  },
  mage: {
    id: 'mage', name: 'Mage', baseAttack: 16,
    baseHp: 90, hpPerLevel: 7,
    baseResource: 110, resourcePerLevel: 11, resourceName: 'Mana',
    baseArmor: 4,
  },
  druid: {
    id: 'druid', name: 'Druid', baseAttack: 9,
    baseHp: 100, hpPerLevel: 8,
    baseResource: 100, resourcePerLevel: 10, resourceName: 'Mana',
    baseArmor: 5,
  },
  assassin: {
    id: 'assassin', name: 'Assassin', baseAttack: 18,
    baseHp: 100, hpPerLevel: 8,
    baseResource: 70, resourcePerLevel: 6, resourceName: 'Momentum',
    baseArmor: 5,
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
  attack: number;
  armor: number;
  gold: number;
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
  stats.expToNext = expToNextLevel(stats.level);
}
