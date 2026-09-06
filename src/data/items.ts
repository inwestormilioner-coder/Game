import type { ClassId, EquipSlot } from '../types';

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
};
