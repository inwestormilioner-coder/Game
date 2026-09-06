import type { ClassId } from '../types';

/**
 * All fields are optional and composable — an ability can combine, say, damage
 * with a slow (Crippling Shot) rather than needing a separate "kind" enum per
 * combination. Game.ts applies whichever fields are present.
 */
export interface AbilityEffect {
  /** Multiplies the caster's effectiveAttack for a single target, or every target in aoeRadius. */
  damageMultiplier?: number;
  /** If set, damage (via damageMultiplier) hits every alive monster within this radius of the target/caster. */
  aoeRadius?: number;
  /** Self-heal, as a fraction of max HP. */
  healPercent?: number;
  /** Self-buff: temporary % increase to effective attack, lasting buffDuration seconds. */
  buffAttackPercent?: number;
  /** Self-buff: temporary % increase to effective armor, lasting buffDuration seconds. */
  buffArmorPercent?: number;
  buffDuration?: number;
  /** Target monster can't move or act for this many seconds. */
  stunDuration?: number;
  /** Target monster's move speed is reduced by this fraction for slowDuration seconds. */
  slowPercent?: number;
  slowDuration?: number;
  /** Moves the caster this many world units toward or away from the current target. */
  dashDistance?: number;
  dashDirection?: 'toward' | 'away';
}

export interface AbilityDef {
  id: string;
  name: string;
  icon: string;
  resourceCost: number;
  cooldown: number;
  /** Max distance to the target for anything with damageMultiplier/stunDuration/slowPercent. */
  range: number;
  effect: AbilityEffect;
}

export const ABILITIES: Record<string, AbilityDef> = {
  // ---- Knight (Fervor, melee) ----
  shieldBash: {
    id: 'shieldBash', name: 'Shield Bash', icon: '🛡️',
    resourceCost: 15, cooldown: 6, range: 2.4,
    effect: { damageMultiplier: 1.2, stunDuration: 2 },
  },
  cleave: {
    id: 'cleave', name: 'Cleave', icon: '🌀',
    resourceCost: 25, cooldown: 8, range: 2.4,
    effect: { damageMultiplier: 0.8, aoeRadius: 3 },
  },
  fortify: {
    id: 'fortify', name: 'Fortify', icon: '🧱',
    resourceCost: 20, cooldown: 15, range: 0,
    effect: { buffArmorPercent: 0.5, buffDuration: 10 },
  },
  secondWind: {
    id: 'secondWind', name: 'Second Wind', icon: '💚',
    resourceCost: 30, cooldown: 20, range: 0,
    effect: { healPercent: 0.25 },
  },
  warcry: {
    id: 'warcry', name: 'Warcry', icon: '📯',
    resourceCost: 20, cooldown: 15, range: 0,
    effect: { buffAttackPercent: 0.3, buffDuration: 10 },
  },

  // ---- Archer (Focus, ranged) ----
  aimedShot: {
    id: 'aimedShot', name: 'Aimed Shot', icon: '🎯',
    resourceCost: 20, cooldown: 5, range: 6,
    effect: { damageMultiplier: 1.5 },
  },
  multishot: {
    id: 'multishot', name: 'Multishot', icon: '🏹',
    resourceCost: 25, cooldown: 9, range: 6,
    effect: { damageMultiplier: 0.7, aoeRadius: 3.5 },
  },
  cripplingShot: {
    id: 'cripplingShot', name: 'Crippling Shot', icon: '🥶',
    resourceCost: 15, cooldown: 10, range: 6,
    effect: { damageMultiplier: 1.0, slowPercent: 0.4, slowDuration: 5 },
  },
  evasiveRoll: {
    id: 'evasiveRoll', name: 'Evasive Roll', icon: '💨',
    resourceCost: 10, cooldown: 8, range: 0,
    effect: { dashDistance: 4, dashDirection: 'away' },
  },
  focusAim: {
    id: 'focusAim', name: 'Focus Aim', icon: '👁️',
    resourceCost: 20, cooldown: 15, range: 0,
    effect: { buffAttackPercent: 0.35, buffDuration: 10 },
  },

  // ---- Mage (Mana, ranged magic) ----
  firebolt: {
    id: 'firebolt', name: 'Firebolt', icon: '🔥',
    resourceCost: 20, cooldown: 4, range: 6,
    effect: { damageMultiplier: 1.6 },
  },
  fireball: {
    id: 'fireball', name: 'Fireball', icon: '☄️',
    resourceCost: 35, cooldown: 10, range: 6,
    effect: { damageMultiplier: 0.9, aoeRadius: 4 },
  },
  frostNova: {
    id: 'frostNova', name: 'Frost Nova', icon: '❄️',
    resourceCost: 30, cooldown: 14, range: 6,
    effect: { damageMultiplier: 0.5, aoeRadius: 3.5, stunDuration: 2 },
  },
  arcaneShield: {
    id: 'arcaneShield', name: 'Arcane Shield', icon: '🔮',
    resourceCost: 25, cooldown: 18, range: 0,
    effect: { buffArmorPercent: 0.8, buffDuration: 8 },
  },
  blink: {
    id: 'blink', name: 'Blink', icon: '⚡',
    resourceCost: 15, cooldown: 10, range: 0,
    effect: { dashDistance: 5, dashDirection: 'toward' },
  },

  // ---- Druid (Mana, support/control) ----
  wrath: {
    id: 'wrath', name: 'Wrath', icon: '🌿',
    resourceCost: 20, cooldown: 5, range: 6,
    effect: { damageMultiplier: 1.3 },
  },
  brambleGrowth: {
    id: 'brambleGrowth', name: 'Bramble Growth', icon: '🌵',
    resourceCost: 30, cooldown: 12, range: 6,
    effect: { damageMultiplier: 0.6, aoeRadius: 3.5, slowPercent: 0.3, slowDuration: 5 },
  },
  thornSnare: {
    id: 'thornSnare', name: 'Thorn Snare', icon: '🌱',
    resourceCost: 20, cooldown: 10, range: 6,
    effect: { damageMultiplier: 0.8, stunDuration: 2.5 },
  },
  regrowth: {
    id: 'regrowth', name: 'Regrowth', icon: '💚',
    resourceCost: 25, cooldown: 8, range: 0,
    effect: { healPercent: 0.3 },
  },
  verdantWard: {
    id: 'verdantWard', name: 'Verdant Ward', icon: '🍃',
    resourceCost: 25, cooldown: 15, range: 0,
    effect: { buffArmorPercent: 0.5, buffDuration: 10 },
  },

  // ---- Assassin (Momentum, melee burst) ----
  backstab: {
    id: 'backstab', name: 'Backstab', icon: '🗡️',
    resourceCost: 30, cooldown: 6, range: 2.4,
    effect: { damageMultiplier: 2.0 },
  },
  shadowStep: {
    id: 'shadowStep', name: 'Shadow Step', icon: '👤',
    resourceCost: 20, cooldown: 8, range: 0,
    effect: { dashDistance: 4, dashDirection: 'toward' },
  },
  fanOfKnives: {
    id: 'fanOfKnives', name: 'Fan of Knives', icon: '🔪',
    resourceCost: 25, cooldown: 10, range: 2.4,
    effect: { damageMultiplier: 0.7, aoeRadius: 3 },
  },
  cripplingStrike: {
    id: 'cripplingStrike', name: 'Crippling Strike', icon: '🥶',
    resourceCost: 15, cooldown: 9, range: 2.4,
    effect: { damageMultiplier: 1.0, slowPercent: 0.4, slowDuration: 4 },
  },
  adrenaline: {
    id: 'adrenaline', name: 'Adrenaline', icon: '⚡',
    resourceCost: 20, cooldown: 15, range: 0,
    effect: { buffAttackPercent: 0.4, buffDuration: 8 },
  },
};

/** Loadout A only for now — Loadout B is an empty, switchable placeholder (GDD Section 10). */
export const CLASS_LOADOUT_A: Record<ClassId, string[]> = {
  knight: ['shieldBash', 'cleave', 'fortify', 'secondWind', 'warcry'],
  archer: ['aimedShot', 'multishot', 'cripplingShot', 'evasiveRoll', 'focusAim'],
  mage: ['firebolt', 'fireball', 'frostNova', 'arcaneShield', 'blink'],
  druid: ['wrath', 'brambleGrowth', 'thornSnare', 'regrowth', 'verdantWard'],
  assassin: ['backstab', 'shadowStep', 'fanOfKnives', 'cripplingStrike', 'adrenaline'],
};
