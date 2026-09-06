export interface ItemDef {
  id: string;
  name: string;
  /** Kilograms — counts against the character's carry capacity (GDD Section 2.5). */
  weight: number;
}

export const ITEMS: Record<string, ItemDef> = {
  grubIchor: { id: 'grubIchor', name: 'Grub Ichor', weight: 0.2 },
  wolfPelt: { id: 'wolfPelt', name: 'Wolf Pelt', weight: 3.0 },
  wolfFang: { id: 'wolfFang', name: 'Wolf Fang', weight: 0.3 },
  alphasFang: { id: 'alphasFang', name: "Alpha's Fang", weight: 0.5 },
  goblinEar: { id: 'goblinEar', name: 'Goblin Ear', weight: 0.1 },
  rustyDagger: { id: 'rustyDagger', name: 'Rusty Dagger', weight: 1.2 },
  boarHide: { id: 'boarHide', name: 'Boar Hide', weight: 4.0 },
  boarTusk: { id: 'boarTusk', name: 'Boar Tusk', weight: 0.8 },
};
