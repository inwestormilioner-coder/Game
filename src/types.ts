export interface Stats {
  level: number;
  hp: number;
  maxHp: number;
  exp: number;
  expToNext: number;
  attack: number;
  gold: number;
}

export function expToNextLevel(level: number): number {
  return Math.round(40 * Math.pow(level, 1.5));
}

export function createInitialStats(): Stats {
  return {
    level: 1,
    hp: 100,
    maxHp: 100,
    exp: 0,
    expToNext: expToNextLevel(1),
    attack: 12,
    gold: 0,
  };
}
