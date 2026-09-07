import type { ClassId, EquipSlot, GatherKind } from '../types';

export interface ItemDef {
  id: string;
  name: string;
  /** Kilograms — counts against the character's carry capacity (GDD Section 2.5). */
  weight: number;
  /** Present only on equippable gear. */
  equip?: {
    slot: EquipSlot;
    attackBonus?: number;
    armorBonus?: number;
    /** Bonus to the class's resource pool (Mana/Fervor/Focus/Momentum) — mostly amulets/reagent pouches. */
    resourceBonus?: number;
    /** If set, only these classes can equip it (arrows/essence are physical, class-tied — GDD Section 26). */
    classes?: ClassId[];
  };
  /** Present only on food — eating it consumes one and applies these effects (GDD Section 6). */
  food?: {
    satietySeconds: number;
    /** Both present together or not at all — a poisonous food always poisons, never a random chance. */
    poisonDamagePerTick?: number;
    poisonTicks?: number;
  };
  /** Present only on gathering tools (pickaxe/hatchet/rod) — carried, not equipped. The highest
   * tier owned gates which gathering-node tier can be attempted at all (gathering professions). */
  tool?: { kind: GatherKind; tier: number };
  /** Present only on fishing bait — consumed one per successful cast; its tier, together with
   * the rod's, caps which fish tier a cast can land. */
  bait?: { tier: number };
}

export const ITEMS: Record<string, ItemDef> = {
  grubIchor: { id: 'grubIchor', name: 'Grub Ichor', weight: 0.2 },
  wolfPelt: { id: 'wolfPelt', name: 'Wolf Pelt', weight: 3.0 },
  wolfFang: { id: 'wolfFang', name: 'Wolf Fang', weight: 0.3 },
  alphasFang: { id: 'alphasFang', name: "Alpha's Fang", weight: 0.5 },
  goblinEar: { id: 'goblinEar', name: 'Goblin Ear', weight: 0.1 },
  rustyDagger: {
    id: 'rustyDagger', name: 'Rusty Dagger', weight: 1.2,
    equip: { slot: 'weapon', attackBonus: 3 },
  },
  leatherCap: {
    id: 'leatherCap', name: 'Leather Cap', weight: 1.0,
    equip: { slot: 'helmet', armorBonus: 2 },
  },
  raggedGloves: {
    id: 'raggedGloves', name: 'Ragged Gloves', weight: 0.6,
    equip: { slot: 'gloves', armorBonus: 1 },
  },
  woodenBuckler: {
    id: 'woodenBuckler', name: 'Wooden Buckler', weight: 3.5,
    equip: { slot: 'shield', armorBonus: 3 },
  },
  copperAmulet: {
    id: 'copperAmulet', name: 'Copper Amulet', weight: 0.3,
    equip: { slot: 'amulet', resourceBonus: 15 },
  },
  huntersQuiver: {
    id: 'huntersQuiver', name: "Hunter's Quiver", weight: 2.0,
    equip: { slot: 'ammo', classes: ['archer'] },
  },
  essencePouch: {
    id: 'essencePouch', name: 'Essence Pouch', weight: 0.5,
    equip: { slot: 'ammo', classes: ['mage', 'druid'], resourceBonus: 10 },
  },
  travelersCape: {
    id: 'travelersCape', name: "Traveler's Cape", weight: 1.8,
    equip: { slot: 'cape', armorBonus: 2 },
  },
  boarHide: { id: 'boarHide', name: 'Boar Hide', weight: 4.0 },
  boarTusk: { id: 'boarTusk', name: 'Boar Tusk', weight: 0.8 },
  boarhideVest: {
    id: 'boarhideVest', name: 'Boarhide Vest', weight: 5.5,
    equip: { slot: 'armor', armorBonus: 4 },
  },
  leatherLegs: {
    id: 'leatherLegs', name: 'Leather Leggings', weight: 2.2,
    equip: { slot: 'legs', armorBonus: 2 },
  },
  wornBoots: {
    id: 'wornBoots', name: 'Worn Boots', weight: 1.4,
    equip: { slot: 'boots', armorBonus: 1 },
  },
  rawMeat: {
    id: 'rawMeat', name: 'Raw Meat', weight: 1.5,
    food: { satietySeconds: 900 }, // 15 min
  },
  // Foraged fruit/berries (safe and poisonous alike) as their own forageable
  // node type are still a later pass — poisonBerries exists so the poison
  // mechanic is testable via monster loot, not because it's gathered yet.
  poisonBerries: {
    id: 'poisonBerries', name: 'Poison Berries', weight: 0.2,
    food: { satietySeconds: 300, poisonDamagePerTick: 1, poisonTicks: 10 }, // 5 min fed, 20s poison
  },

  // ---- Gathering professions: tools, bait, and their yields ----
  rustyPickaxe: { id: 'rustyPickaxe', name: 'Rusty Pickaxe', weight: 2.5, tool: { kind: 'mining', tier: 1 } },
  sturdyPickaxe: { id: 'sturdyPickaxe', name: 'Sturdy Pickaxe', weight: 3.2, tool: { kind: 'mining', tier: 2 } },
  rustyHatchet: { id: 'rustyHatchet', name: 'Rusty Hatchet', weight: 2.0, tool: { kind: 'woodcutting', tier: 1 } },
  sturdyHatchet: { id: 'sturdyHatchet', name: 'Sturdy Hatchet', weight: 2.6, tool: { kind: 'woodcutting', tier: 2 } },
  simpleFishingRod: { id: 'simpleFishingRod', name: 'Simple Fishing Rod', weight: 1.2, tool: { kind: 'fishing', tier: 1 } },
  sturdyFishingRod: { id: 'sturdyFishingRod', name: 'Sturdy Fishing Rod', weight: 1.6, tool: { kind: 'fishing', tier: 2 } },
  earthworms: { id: 'earthworms', name: 'Earthworms', weight: 0.05, bait: { tier: 1 } },
  fatWorms: { id: 'fatWorms', name: 'Fat Worms', weight: 0.05, bait: { tier: 2 } },

  copperOre: { id: 'copperOre', name: 'Copper Ore', weight: 2.0 },
  ironOre: { id: 'ironOre', name: 'Iron Ore', weight: 2.8 },
  rawLog: { id: 'rawLog', name: 'Raw Log', weight: 3.0 },
  oakLog: { id: 'oakLog', name: 'Oak Log', weight: 3.6 },
  minnow: {
    id: 'minnow', name: 'Minnow', weight: 0.4,
    food: { satietySeconds: 400 },
  },
  trout: {
    id: 'trout', name: 'Trout', weight: 0.9,
    food: { satietySeconds: 700 },
  },
};
