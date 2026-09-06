export interface ItemDef {
  id: string;
  name: string;
}

export const ITEMS: Record<string, ItemDef> = {
  grubIchor: { id: 'grubIchor', name: 'Grub Ichor' },
  wolfPelt: { id: 'wolfPelt', name: 'Wolf Pelt' },
  wolfFang: { id: 'wolfFang', name: 'Wolf Fang' },
  alphasFang: { id: 'alphasFang', name: "Alpha's Fang" },
  goblinEar: { id: 'goblinEar', name: 'Goblin Ear' },
  rustyDagger: { id: 'rustyDagger', name: 'Rusty Dagger' },
  boarHide: { id: 'boarHide', name: 'Boar Hide' },
  boarTusk: { id: 'boarTusk', name: 'Boar Tusk' },
};
