import type { GatherKind } from '../types';

export interface GatherNodeDef {
  id: string;
  kind: GatherKind;
  /** 1 = always-accessible; 2 = the harder tier, gated behind both a higher skill
   * level (to attempt at all) and a better tool/bait (to succeed). */
  tier: number;
  requiredSkillLevel: number;
  x: number;
  z: number;
  /** Base seconds between attempts at this node — the skill-level cooldown
   * reduction (Player.tryGather) is what makes a higher level "faster". */
  baseGatherSeconds: number;
  yieldItemId: string;
  yieldQtyMin: number;
  yieldQtyMax: number;
  respawnDelay: number;
}

// Two tiers per profession: a tier-1 node anyone can start on, a tier-2 node that
// needs both a higher skill level and a better tool (rod+bait for fishing) —
// exactly the "harder mine / better pickaxe -> better stone" shape the design calls for.
export const GATHER_NODES: Record<string, GatherNodeDef> = {
  copperVein: {
    id: 'copperVein', kind: 'mining', tier: 1, requiredSkillLevel: 0,
    x: -16, z: 10, baseGatherSeconds: 3,
    yieldItemId: 'copperOre', yieldQtyMin: 1, yieldQtyMax: 2, respawnDelay: 20,
  },
  ironVein: {
    id: 'ironVein', kind: 'mining', tier: 2, requiredSkillLevel: 15,
    x: -19, z: 13, baseGatherSeconds: 4,
    yieldItemId: 'ironOre', yieldQtyMin: 1, yieldQtyMax: 2, respawnDelay: 30,
  },
  birchTree: {
    id: 'birchTree', kind: 'woodcutting', tier: 1, requiredSkillLevel: 0,
    x: 16, z: -10, baseGatherSeconds: 3,
    yieldItemId: 'rawLog', yieldQtyMin: 1, yieldQtyMax: 2, respawnDelay: 20,
  },
  oakTree: {
    id: 'oakTree', kind: 'woodcutting', tier: 2, requiredSkillLevel: 15,
    x: 19, z: -13, baseGatherSeconds: 4,
    yieldItemId: 'oakLog', yieldQtyMin: 1, yieldQtyMax: 2, respawnDelay: 30,
  },
  shallowFishingSpot: {
    id: 'shallowFishingSpot', kind: 'fishing', tier: 1, requiredSkillLevel: 0,
    x: 18, z: 18, baseGatherSeconds: 3,
    yieldItemId: 'minnow', yieldQtyMin: 1, yieldQtyMax: 1, respawnDelay: 15,
  },
  deepFishingSpot: {
    id: 'deepFishingSpot', kind: 'fishing', tier: 2, requiredSkillLevel: 15,
    x: 21, z: 20, baseGatherSeconds: 4,
    yieldItemId: 'trout', yieldQtyMin: 1, yieldQtyMax: 1, respawnDelay: 25,
  },
};
