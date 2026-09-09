import type { LootEntry } from '../systems/loot';

// GDD Section 11: monsters have no character level. Difficulty comes from
// these hand-authored stats/behavior, not a scaling number.
export type MonsterBehavior = 'passive' | 'aggressive';

export interface MonsterDef {
  id: string;
  name: string;
  hp: number;
  damageMin: number;
  damageMax: number;
  attackRange: number;
  aggroRange: number;
  moveSpeed: number;
  attackCooldown: number;
  respawnDelay: number;
  xp: number;
  goldMin: number;
  goldMax: number;
  behavior: MonsterBehavior;
  /** Placeholder look until real art lands: a flat color + size per type. */
  color: number;
  radius: number;
  lootTable: LootEntry[];
  /** Real model (Meshy.ai + Mixamo export, same pipeline as the player — GDD Section 28).
   * Optional; types without one yet keep the placeholder sphere. */
  modelPath?: string;
  /** Mixamo interpreted our export's units as centimeters rather than meters for this
   * asset, so its whole rig came back 100x too small — corrected on load, not baked
   * into the file, so it's visible/documented here rather than hidden in the asset. */
  modelScale?: number;
}

export const MONSTER_DEFS: Record<string, MonsterDef> = {
  mudclawGrub: {
    id: 'mudclawGrub',
    name: 'Mudclaw Grub',
    hp: 20,
    damageMin: 2,
    damageMax: 4,
    attackRange: 1.2,
    aggroRange: 2.4,
    moveSpeed: 0.4,
    attackCooldown: 1.4,
    respawnDelay: 5,
    xp: 4,
    goldMin: 0,
    goldMax: 1,
    behavior: 'passive',
    color: 0x8a6a3a,
    radius: 0.35,
    lootTable: [{ itemId: 'grubIchor', rarity: 'guaranteed', chance: 1, qtyMin: 1, qtyMax: 1 }],
  },
  brambleWolf: {
    id: 'brambleWolf',
    name: 'Bramble Wolf',
    hp: 45,
    damageMin: 5,
    damageMax: 9,
    attackRange: 1.6,
    aggroRange: 4.5,
    moveSpeed: 0.9,
    attackCooldown: 1.1,
    respawnDelay: 8,
    xp: 14,
    goldMin: 1,
    goldMax: 3,
    behavior: 'aggressive',
    color: 0x6b6b6b,
    radius: 0.45,
    lootTable: [
      { itemId: 'wolfPelt', rarity: 'common', chance: 0.4, qtyMin: 1, qtyMax: 1 },
      { itemId: 'wolfFang', rarity: 'common', chance: 0.3, qtyMin: 1, qtyMax: 2 },
      { itemId: 'alphasFang', rarity: 'rare', chance: 0.02, qtyMin: 1, qtyMax: 1 },
      { itemId: 'rawMeat', rarity: 'common', chance: 0.5, qtyMin: 1, qtyMax: 1 },
    ],
  },
  ashfenGoblin: {
    id: 'ashfenGoblin',
    name: 'Ashfen Goblin',
    hp: 60,
    damageMin: 6,
    damageMax: 11,
    attackRange: 1.6,
    aggroRange: 4,
    moveSpeed: 0.75,
    attackCooldown: 1.0,
    respawnDelay: 10,
    xp: 20,
    goldMin: 2,
    goldMax: 5,
    behavior: 'aggressive',
    color: 0x4a7a3a,
    radius: 0.42,
    // A humanoid raider, unlike the wolf/boar/grub — plausibly carries or has
    // looted crafted gear from past victims, including a lost quiver or pouch.
    lootTable: [
      { itemId: 'goblinEar', rarity: 'common', chance: 0.45, qtyMin: 1, qtyMax: 1 },
      { itemId: 'rustyDagger', rarity: 'uncommon', chance: 0.12, qtyMin: 1, qtyMax: 1 },
      { itemId: 'leatherCap', rarity: 'uncommon', chance: 0.1, qtyMin: 1, qtyMax: 1 },
      { itemId: 'raggedGloves', rarity: 'common', chance: 0.2, qtyMin: 1, qtyMax: 1 },
      { itemId: 'woodenBuckler', rarity: 'rare', chance: 0.04, qtyMin: 1, qtyMax: 1 },
      { itemId: 'copperAmulet', rarity: 'rare', chance: 0.03, qtyMin: 1, qtyMax: 1 },
      { itemId: 'huntersQuiver', rarity: 'rare', chance: 0.03, qtyMin: 1, qtyMax: 1 },
      { itemId: 'essencePouch', rarity: 'rare', chance: 0.03, qtyMin: 1, qtyMax: 1 },
      { itemId: 'travelersCape', rarity: 'veryRare', chance: 0.01, qtyMin: 1, qtyMax: 1 },
    ],
    modelPath: '/models/goblin/goblin.glb',
    modelScale: 100,
  },
  ironhideBoar: {
    id: 'ironhideBoar',
    name: 'Ironhide Boar',
    hp: 90,
    damageMin: 10,
    damageMax: 16,
    attackRange: 1.8,
    aggroRange: 3.5,
    moveSpeed: 1.0,
    attackCooldown: 1.3,
    respawnDelay: 14,
    xp: 28,
    goldMin: 3,
    goldMax: 7,
    behavior: 'aggressive',
    color: 0x5a4030,
    radius: 0.55,
    lootTable: [
      { itemId: 'boarHide', rarity: 'common', chance: 0.5, qtyMin: 1, qtyMax: 1 },
      { itemId: 'boarTusk', rarity: 'uncommon', chance: 0.15, qtyMin: 1, qtyMax: 2 },
      { itemId: 'boarhideVest', rarity: 'rare', chance: 0.05, qtyMin: 1, qtyMax: 1 },
      { itemId: 'leatherLegs', rarity: 'uncommon', chance: 0.12, qtyMin: 1, qtyMax: 1 },
      { itemId: 'wornBoots', rarity: 'uncommon', chance: 0.12, qtyMin: 1, qtyMax: 1 },
      { itemId: 'rawMeat', rarity: 'common', chance: 0.6, qtyMin: 1, qtyMax: 2 },
    ],
  },
};
