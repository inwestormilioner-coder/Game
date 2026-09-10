// Loot rarity system (GDD Section 12). Ultra-rare/quest/boss-exclusive
// tiers aren't needed yet — this is deliberately the small subset the
// current monster roster actually uses; extend the union as new tiers
// become relevant rather than pre-building them unused.
export type LootRarity = 'guaranteed' | 'common' | 'uncommon' | 'rare' | 'veryRare';

export interface LootEntry {
  itemId: string;
  rarity: LootRarity;
  /** Drop chance 0..1. Ignored (treated as 1) when rarity is 'guaranteed'. */
  chance: number;
  qtyMin: number;
  qtyMax: number;
}

export interface LootDrop {
  itemId: string;
  qty: number;
}

/** Rolls each table entry independently — a kill can drop several items at once. */
export function rollLoot(table: LootEntry[]): LootDrop[] {
  const drops: LootDrop[] = [];
  for (const entry of table) {
    if (entry.rarity !== 'guaranteed' && Math.random() >= entry.chance) continue;
    const qty = entry.qtyMin + Math.floor(Math.random() * (entry.qtyMax - entry.qtyMin + 1));
    if (qty > 0) drops.push({ itemId: entry.itemId, qty });
  }
  return drops;
}
