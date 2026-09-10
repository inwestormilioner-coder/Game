export interface QuestDef {
  id: string;
  giverId: string;
  name: string;
  /** Dialogue shown before the player has accepted (GDD Section 15: delivered diegetically, not a log entry). */
  offerText: string;
  /** Shown if the giver is talked to again while the quest is still in progress. */
  activeText: string;
  /** Shown at the giver once the target count is met, right before turning in. */
  turnInText: string;
  /** Becomes the permanent journal line once turned in — text the player learned, not a waypoint. */
  completeText: string;
  targetMonsterId: string;
  targetCount: number;
  rewardXp: number;
  rewardGold: number;
  rewardItemId?: string;
}

export const QUESTS: Record<string, QuestDef> = {
  cullTheGrubs: {
    id: 'cullTheGrubs',
    giverId: 'elderMara',
    name: 'Cull the Grubs',
    offerText:
      "The mudclaw grubs have gotten into the grain stores again. Thin their numbers — five ought to send a message — and I'll make it worth your while.",
    activeText: 'Still counting on you to thin out those grubs. Five of them, remember.',
    turnInText: 'Five grubs, just like that? The stores thank you. Here — take this for your trouble.',
    completeText: "Elder Mara's grubs are dealt with, for now.",
    targetMonsterId: 'mudclawGrub',
    targetCount: 5,
    rewardXp: 150,
    rewardGold: 40,
    rewardItemId: 'leatherCap',
  },
};
