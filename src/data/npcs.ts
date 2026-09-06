export type NpcRole = 'quest' | 'depot' | 'ferryman';

export interface NpcDef {
  id: string;
  name: string;
  role: NpcRole;
  x: number;
  z: number;
  color: number;
  /** Shown when there's nothing further to offer right now (no/active quest, or just used the depot/ferry). */
  idleText: string;
  /** Ferryman only — the dock this NPC sails to, and the Glint fare (GDD Section 16). */
  destination?: { x: number; z: number; name: string };
  fare?: number;
}

// GDD Section 32 MVP scope: "1 city (Duskmere): Temple, Depot, 1 NPC general-goods
// shop, 1 travel NPC (a working ship route to a placeholder second dock)". The
// general-goods shop is still to come; quest-giver + Depot + Ferryman are this pass.
export const NPCS: Record<string, NpcDef> = {
  elderMara: {
    id: 'elderMara',
    name: 'Elder Mara',
    role: 'quest',
    x: -3,
    z: -2,
    color: 0xd4af37,
    idleText: 'The grain stores are holding, for now. Come back if that changes.',
  },
  orinTheKeeper: {
    id: 'orinTheKeeper',
    name: 'Orin the Keeper',
    role: 'depot',
    x: -3,
    z: -5,
    color: 0x6699cc,
    idleText: 'Your stash is safe with me, as always.',
  },
  ferrymanBrack: {
    id: 'ferrymanBrack',
    name: 'Ferryman Brack',
    role: 'ferryman',
    x: 34,
    z: 0,
    color: 0x8899aa,
    idleText: 'Fair winds. Say the word and I’ll take you across.',
    destination: { x: -34, z: 0, name: 'Ravensport Dock' },
    fare: 10,
  },
  ferrymanRill: {
    id: 'ferrymanRill',
    name: 'Ferryman Rill',
    role: 'ferryman',
    x: -34,
    z: 0,
    color: 0x8899aa,
    idleText: 'Ready whenever you are — Duskmere’s just across the water.',
    destination: { x: 34, z: 0, name: 'Duskmere Dock' },
    fare: 10,
  },
};
