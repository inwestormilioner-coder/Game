# THORNREACH — Game Design Document (v0.1)

**Working title:** *Thornreach: Chronicles of the Sundered Isles*
**Genre:** Persistent open-world fantasy MMORPG, mobile-first (iOS/Android/tablet)
**Status:** Foundational design — pre-implementation
**Author:** Lead Design/Systems Architecture pass
**Scope of this document:** Full systems design for the long-term game, plus a scoped MVP ("vertical slice") to build first. No copyrighted names, art, sprites, sounds, or IP from Tibia, Mobile Legends, or any other title are used anywhere in this document. All names below (world, classes' flavor, monsters, items, spells) are original and invented for this project.

> Every section below states **why the system exists**, **how it works mechanically**, **what problem it solves**, **what can go wrong**, and **how it scales to thousands of concurrent players**, for every system load-bearing enough to warrant it. Smaller/supporting systems get a lighter treatment.

---

## Table of Contents

0. Core Philosophy & Pillars
1. World & Setting Primer (original IP)
2. Character Classes
3. Core Attributes
4. Experience & Leveling Formula
5. Skill Progression Formula
6. Combat Resource Systems
7. Movement Speed Formula
8. Combat, Targeting & Abilities
9. Rune System
10. Mobile Combat UI
11. Monster Architecture (no monster levels)
12. Loot Table & Rarity System
13. Hunting / EXP Design
14. Party System & Shared XP Formula
15. Quest System Architecture
16. World Architecture & Travel
17. NPC System
18. Depot / Storage
19. Temple & Respawn
20. Death & Corpse System
21. PvP / PK System
22. Find-Player Spell
23. Social Systems
24. Guilds
25. Economy
26. Item System
27. Combat Philosophy Summary
28. Visual Style & Camera
29. Long-Term Progression Milestones
30. MVP — Vertical Slice
31. Development Order
32. Risks, Open Questions & Live-Ops Levers

---

## 0. Core Philosophy & Pillars

**Thesis:** *"Old-school MMORPG progression and freedom, redesigned from the ground up for modern mobile devices."*

Four pillars, in priority order:

1. **Progression is the game.** There is no level cap. Advancement is slow, deliberate, and always meaningful — a level-up at level 5 and a level-up at level 150 should both feel like an event, not a rounding error. We optimize for a multi-year retention curve, not a multi-week one.
2. **The world is real, not a menu.** Travel, danger, and discovery happen by walking/sailing through the world. No fast-travel-everywhere, no quest arrows walking players by the hand.
3. **Danger has teeth.** Death costs something. Open-world PvP is possible everywhere outside safe zones. Risk vs. reward is the core hunting decision every session.
4. **Modern mobile ergonomics, old-school mobile depth.** Touch controls (virtual joystick, tap-to-target, drag-to-cast) must feel as good as a modern mobile MOBA, while the systems underneath remain as deep as a classic PC MMORPG.

**Non-goals:** battle pass power creep, gacha power progression, PvE queue matchmaking, auto-battle/auto-path to grind, pay-to-instantly-level. Monetization (out of scope for this document) should sell convenience/cosmetics/storage, never bypass the slow-progression pillar — that pillar *is* the retention engine.

---

## 1. World & Setting Primer (original IP)

To ground later systems with concrete original names (never Tibia/MOBA IP):

- **World name:** Vaeloria — a fractured continent-and-archipelago setting recovering from a magical cataclysm ("The Sundering") centuries ago.
- **Starting city:** Duskmere — walled trade city on the mainland coast, home of the starting Temple, Depot, and NPC shops.
- **Second city (mid-game, reachable by ship):** Ravensport — harbor city, guild hub, auction house.
- **Starting wilderness:** The Hollow Wilds — forest/plains ring around Duskmere, low-danger hunting.
- **First dungeon:** The Sunken Barrow — collapsed crypt beneath the Hollow Wilds, mid-danger.
- **Open PvP frontier zone (later content):** The Bloodmarsh Frontier — contested wilderness between factions, no guards.
- **Currency:** Glints (gold coins), Slivers (silver, 1 Glint = 100 Slivers).
- **Core factions (long-term):** none forced at launch; guild politics drive conflict rather than lore-mandated races/nations, keeping early content simple and IP-safe.

This section exists purely to give every later formula and system a concrete, ownable name to hang off — expand freely during content production without touching systems design.

---

## 2. Character Classes

All five classes share the same attribute model (Section 3) and level curve (Section 4); they differ in **base stat weighting, skill growth rates, resource system, and ability kits**. Every class must be viable solo and in groups, with a clearly different risk profile.

### 2.1 Class Identity Matrix

| Class | Role | Survivability | Damage type | Damage output | Mobility |
|---|---|---|---|---|---|
| Knight | Tank / frontline | Very High | Melee physical | Low–Medium | Low |
| Archer | Ranged DPS / skirmisher | Medium | Ranged physical | Medium–High (sustained) | Medium |
| Mage | Burst caster | Very Low | Magic (AoE) | Very High | Low |
| Druid | Support / controller | Low | Magic (utility) | Low–Medium | Low |
| Assassin | Melee burst / duelist | Very Low | Melee physical (burst) | Very High (single target) | Very High |

### 2.2 Per-Class Weapon/Utility Skills

Original skill names (avoiding any existing game's terminology):

- **Knight:** Blade Fighting, Axe Fighting, Bludgeon Fighting (mace-equivalent), Wardcraft (shielding)
- **Archer:** Marksmanship (bow/crossbow distance skill), Wardcraft, Blade Fighting (secondary melee)
- **Mage:** Arcane Level (magic level equivalent), Wardcraft
- **Druid:** Arcane Level, Wardcraft
- **Assassin:** Talon Fighting (dedicated dagger/claw weapon skill), Wardcraft

All classes can train **Arcane Level** (governs spell/rune power and requirements) and **Wardcraft** (governs block chance/amount with a shield or off-hand parry item), but at wildly different rates (Section 5).

### 2.3 Base Stat Growth Per Level

Every class gets a **base value at level 1** and a **per-level growth value** for HP, the primary resource, Attack (LevelBonus, Section 3), and Armor. Growth is linear per level but the *effective* power curve is non-linear because higher levels also grant better equipment access and skill levels — deliberately so; we do not want level alone to trivialize content.

| Class | HP @ L1 | HP / level | Resource @ L1 | Resource / level | Attack @ L1 | Attack / level | Armor @ L1 | Armor / level |
|---|---|---|---|---|---|---|---|---|
| Knight | 180 | +19 | 40 (Rage) | +3 | 14 | +0.2 | 12 | +0.6 |
| Archer | 140 | +13 | 60 (Focus) | +6 | 12 | +0.4 | 8 | +0.3 |
| Mage | 90 | +7 | 110 (Mana) | +11 | 16 | +0.5 | 4 | +0.05 |
| Druid | 100 | +8 | 100 (Mana) | +10 | 9 | +0.25 | 5 | +0.15 |
| Assassin | 100 | +8 | 70 (Momentum) | +6 | 18 | +0.6 | 5 | +0.15 |

`HP(level) = HP@L1 + (level-1) × HP-per-level` (before equipment/buffs). Same linear form for the resource pool, Attack, and Armor. These numbers are first-pass balance constants — expect tuning during playtesting, but the **shape** must be preserved: Knight ≫ others in HP and in Armor/level (its per-level growth is spent on becoming harder to kill, not harder-hitting); Assassin > Mage ≈ Archer > Druid > Knight in Attack/level (raw damage growth belongs to the offensive classes, not the tank); Mage ≪ everyone in Armor/level (a caster in robes barely gets tougher no matter the level).

### 2.4 Design Rationale

- **Why:** distinct, legible archetypes are what make party composition and PvP matchups interesting; a "jack of all trades" class produces homogeneous gameplay.
- **What can go wrong:** if Assassin burst is tuned too high relative to its fragility, it becomes a "delete button" in PvP with no counterplay window; if Knight damage is tuned too low, nobody solo-hunts as Knight and the class becomes party-only. Mitigate with the ability-cooldown and resource-cost levers in Section 6, not by inflating HP/armor.
- **How it scales:** stat formulas are pure functions of level + gear + skills, evaluated server-side per combat tick — no per-class special-cased combat code paths needed at the engine level, which keeps server CPU cost per class identical for thousands of concurrent entities.

### 2.5 Carry Capacity

Every item has a **weight in kilograms**. Every character has a **maximum carry capacity**, also in kilograms, and cannot pick up an item that would push their total carried weight (backpack contents; equipped gear counts too once equipment exists) over that limit — a full backpack is a real, felt constraint, not a slot-count abstraction.

Capacity is a base value at level 1 plus a flat amount gained **every level**, exactly like HP and the resource pool:

```
MaxCapacity(level) = BaseCapacity + (level - 1) × CapacityPerLevel
```

The per-class ordering follows the same physical-identity logic as the rest of the kit: **Knight carries the most** (it's the class built around raw physical strength), **Archer is a close second** (a real logistics reason, not flavor-only — arrows/bolts are a resource per Section 6 and need to be carried in bulk), **Assassin sits in the middle**, and **Mage and Druid tie for the least** (their strength is spent on Arcane Level, not muscle).

| Class | Base Capacity (L1) | Capacity / level |
|---|---|---|
| Knight | 450 kg | +15 kg |
| Archer | 380 kg | +12 kg |
| Assassin | 320 kg | +9 kg |
| Mage | 250 kg | +6 kg |
| Druid | 250 kg | +6 kg |

At level 50 this spreads to Knight 1,185 kg vs. Mage/Druid 544 kg — over double — which is deliberate: a high-level Knight functioning as the party's pack mule for a hunting trip is a real, mechanically-grounded role, not just a tank stereotype.

### What problem it solves
Without a capacity limit, "how much can I carry" isn't a decision — inventory becomes an unlimited pocket dimension and looting stops being a choice. With it, a good hunt forces real trade-offs (take the bulky common pelts for guaranteed coin, or hold space for the one rare drop that might appear) and reinforces class identity outside of combat.

### What can go wrong
A limit that's too tight makes hunting trips tedious (constant depot runs); too loose and it's meaningless. Tune per-item weight so that a normal hunting session's expected loot volume uses roughly half of an appropriately-leveled character's capacity, leaving headroom for a lucky rare-drop haul — this is a live-ops number to watch, not a one-time guess.

---

## 3. Core Attributes

Rather than a free attribute-point system (which invites min-maxing degenerate builds and complicates balance), Thornreach uses **derived stats**: HP, Resource, Armor, and damage are all functions of **Level + Skills + Equipment**, matching the classic philosophy where *skills*, not allocated stat points, are the long-term investment. This keeps the character sheet simple and keeps all "build diversity" in equipment and skill choice, which is far easier to balance at scale than freeform attribute allocation.

Derived combat stats per hit:
- **Melee/Ranged physical damage** = `(WeaponBaseDamage + LevelBonus) × (1 + WeaponSkillLevel / 100) × EquipmentModifiers`
- **Magic damage** = `(SpellBaseDamage + LevelBonus) × (1 + ArcaneLevel / 60) × EquipmentModifiers`
- **LevelBonus** = `floor((Level − 1) × AttackPerLevel)`, where `AttackPerLevel` is per-class (Section 2.3) — deliberately small and flat, never multiplicative, and deliberately *uneven* across classes: Assassin's melee burst and Mage's magic damage climb fastest with level (0.6 and 0.5/level), Archer's ranged damage close behind (0.4), Druid modest (0.25, its identity is support, not damage), and **Knight slowest of all (0.2)** — the Knight's per-level "budget" goes into Armor/level instead (Section 2.3), so it gets steadily harder to kill rather than steadily harder-hitting, matching its tank identity.
- **Mitigation** = `Armor / (Armor + 50)` (a diminishing-returns "armor formula" — 50 armor = 50% reduction, 150 armor = 75%, 450 armor = 90%; asymptotically approaches but never reaches 100%, so there is no such thing as unkillable). Armor also grows per level now (Section 2.3), same `floor((Level-1) × ArmorPerLevel)` shape, again uneven by class: Knight's grows fastest (0.6/level), Mage's is nearly flat (0.05/level) — a caster in robes doesn't get meaningfully tougher just by leveling.

**Level is allowed to add a small, flat amount of damage and armor — never to be the main driver.** The bulk of real damage growth still has to come from WeaponSkillLevel/ArcaneLevel (slow by design, Section 5) and gear; LevelBonus exists so a level-up still feels a little stronger in a fight, without letting level alone collapse time-to-kill. Since HP (Section 2.3) grows noticeably faster with level than LevelBonus does for any class, two same-level, similarly-skilled-and-geared characters should still take a long, real fight to kill each other whether they're level 5 or level 150 — a duel between two max-effort, similarly-equipped players is meant to be a feat, not a two-or-three-hit trade. If a future tuning pass ever makes LevelBonus large enough to rival WeaponSkillLevel's contribution, that has broken this goal and needs to come back down, not be treated as a balance knob to push further.

---

## 4. Experience & Leveling Formula

### Why
This is the single most important number in the game: get it wrong and the whole "months/years of progression" pillar collapses. It must (a) feel fast and generous in the first hour, (b) feel like steady, satisfying work in the first months, and (c) never actually end.

### How it works

We use a **pure power-law cumulative curve** — elegant, monotonic, smooth, and trivially supports uncapped levels without special-casing:

```
TotalXP(L) = floor( 5 × L^3.5 )
```

Where `TotalXP(L)` is the *total* experience required to have reached level `L` from level 1 (`TotalXP(1) = 5`, treated as ≈0). The experience required to go from level `L` to `L+1` is simply:

```
ReqXP(L → L+1) = TotalXP(L+1) − TotalXP(L)
```

This single formula is original to this project (not Tibia's cubic table) but is philosophically aligned: a smoothly accelerating exponent-3.5 power curve, rather than a linear or mild-quadratic one, so that mid/high levels become dramatically more expensive without any awkward piecewise breakpoints.

### Worked table

| Level | TotalXP (cumulative) | XP for *this* level-up | Approx. real-world pacing* |
|---|---|---|---|
| 2 | 57 | 52 | first minutes |
| 5 | 1,398 | ~400 | first session |
| 10 | 15,811 | ~3,600 | first few sessions |
| 15 | 65,589 | ~9,700 | first week |
| 20 | 178,885 | ~19,600 | 2–3 weeks |
| 25 | 390,625 | ~34,000 | ~1 month (casual) |
| 30 | 739,502 | ~54,000 | |
| 40 | 2,024,948 | ~110,000 | |
| **50** | **4,419,417** | **~187,000** | **~1 month of serious, realistic play (~3h/day)** |
| 60 | 8,373,551 | ~283,000 | |
| 75 | 18,268,544 | ~500,000 | several months |
| 100 | 50,000,000 | ~1,140,000 | ~1 year of dedicated play |
| 150 | 206,670,166 | ~4,000,000 | multi-year veteran territory |
| 200 | 565,685,425 | ~9,700,000 | top-tier long-term achievement |
| 300 | 2,332,700,914 | ~34,000,000 | aspirational, server-first territory |

*Pacing assumes an efficient, appropriately-chosen hunting ground and an actively played, non-botting character; see Section 13 for how XP/hour scales with hunting choices. These pacing figures are the *design target* fed into monster XP-reward tuning (Section 11), not hard guarantees — they are the primary live-ops tuning lever (a single global multiplier on monster XP rewards can compress or stretch this curve post-launch without touching the formula).

### What problem it solves
- A single closed-form formula scales to arbitrary level with zero additional design work — level 5,000 "works" mathematically even though no player will ever reach it.
- The `^3.5` exponent guarantees **every doubling of level costs ~11.3× the XP**, and every 50% level increase costs ~4.13× the XP — a clean, self-similar curve that is easy to reason about and easy to re-tune (adjusting the single leading constant `5` uniformly compresses/stretches the entire curve without changing its shape).

### What can go wrong
- If monster XP rewards don't grow (even sub-linearly) at higher-danger content, XP/hour stagnates and high levels become unplayable grinds instead of "hard but rewarding." Mitigation: Section 11's monster XP formula must be tuned in lockstep with this curve, checked via simulation before each content patch.
- Power-law curves can produce ugly rounding at very low levels (level 1→2 costing single-digit XP). This is intentional — the first few levels should be nearly instant, establishing habit and reward loop, before the curve visibly steepens by level ~10–15.

### How it scales to thousands of players
Fully deterministic and stateless per-player — `TotalXP(L)` is computed on demand, not stored as a lookup table, so there's no server memory/DB cost regardless of population size, and no ceiling that a large, veteran playerbase can "run out of."

---

## 5. Skill Progression Formula

### Why
Skills (weapon skills, Wardcraft, Arcane Level) are the *second* progression axis, orthogonal to character level, and the primary way classes differentiate — this is what makes "Level 50 Knight" and "Level 50 Mage" completely different characters mechanically, not just re-skins.

### How it works

Skills advance through **use**, not XP or points: successful hits (weapon skills), successful blocks (Wardcraft), or successful spell casts (Arcane Level) accumulate toward the next skill point. Formula:

```
ActionsToAdvance(S → S+1) = ceil( 6 × Rate × S^1.7 )
```

Where `S` is the current skill level (starting at 10 for weapon skills, 0 for Arcane Level) and `Rate` is a per-class, per-skill multiplier:

| Tier | Rate | Meaning |
|---|---|---|
| VERY FAST | 0.6 | class's signature skill |
| FAST | 0.85 | strong secondary |
| MEDIUM | 1.2 | usable but not focus |
| SLOW | 1.8 | weak, off-class |
| VERY SLOW | 3.0 | actively discouraged |

### Class skill-rate table

| Class | Signature skill (VERY FAST) | Wardcraft | Other melee | Marksmanship | Arcane Level |
|---|---|---|---|---|---|
| Knight | Blade/Axe/Bludgeon — VERY FAST | VERY FAST | — | SLOW | VERY SLOW |
| Archer | Marksmanship — VERY FAST | MEDIUM | MEDIUM/SLOW | — | SLOW |
| Mage | Arcane Level — VERY FAST | VERY SLOW | SLOW | SLOW | — |
| Druid | Arcane Level — VERY FAST | SLOW | SLOW | SLOW | — |
| Assassin | Talon Fighting — VERY FAST | MEDIUM | MEDIUM | SLOW | SLOW |

### Worked example (Knight training Blade Fighting, VERY FAST, Rate 0.6)

| Skill level | Hits needed for next point | Cumulative hits |
|---|---|---|
| 10 → 11 | 30 | 30 |
| 25 → 26 | 143 | ~1,900 |
| 50 → 51 | 464 | ~10,300 |
| 75 → 76 | 954 | ~28,000 |
| 100 → 101 | 1,585 | ~57,000 |

Same Knight training **Distance (Marksmanship)**, SLOW, Rate 1.8 — at skill 50→51: `ceil(6 × 1.8 × 50^1.7) ≈ 1,392` hits, **3× slower** than his own weapon skill at the same level, exactly matching the "poor ranged progression" design intent from Section 2.

A Mage training **Wardcraft**, VERY SLOW, Rate 3.0 — at skill 50→51: `ceil(6 × 3.0 × 50^1.7) ≈ 2,321` hits, roughly **5×** slower than a Knight's Wardcraft (VERY FAST) at the same skill level, cementing "Mage will basically never out-block a Knight."

### Wardcraft mechanics

Wardcraft only does something with a **shield (or off-hand parry item) equipped** — the skill governs how good the block is, not whether one is possible at all; a character with no shield has 0% block chance no matter how high Wardcraft climbs. With one equipped:

```
BlockChance = Wardcraft / (Wardcraft + 200)
```

The same diminishing-returns shape as the armor mitigation formula (Section 3) — asymptotic, never reaches 100%. At the weapon-skill starting level of 10 that's a 4.8% block chance; it takes Wardcraft 200 to reach 50%, and it keeps climbing slowly forever past that. A successful block halves the incoming hit *before* armor mitigation is applied on top, and — per the "advance through use" rule above — only a **successful** block trains Wardcraft; a hit that lands clean teaches nothing.

### What problem it solves
Use-based, exponentially-slowing advancement means skill mastery is a genuine long-term investment (a level-300 character can still have room to grow a favored skill), and the per-class rate table is a single tuning surface — a designer can nudge one number (e.g., Archer's Wardcraft from MEDIUM to SLOW) to retune an entire class's secondary identity without touching any other formula.

### What can go wrong
- If `Rate` spreads are too aggressive, off-class skills become *functionally* impossible to raise (which is fine for cosmetic skills, bad if it locks a class out of viable hybrid builds the design wants to allow, e.g. Archer melee).
- Pure "hits to advance" invites AFK-macro grinding against weak stationary targets. Mitigation: skill gain requires the *target* to be a valid, aggroed hunting-worthy monster (minimum HP/damage-dealt threshold) and gain rate is naturally throttled by attack speed and monster respawn — training dummies exist but grant a heavily reduced rate (10%) intentionally, as a "practice, not grind" outlet.

### How it scales
Same as XP — computed on demand from stored current skill level + accumulated progress counter (two integers per skill per character); trivial DB footprint even at millions of characters.

### Gathering professions (Mining, Fishing, Woodcutting)

Three non-combat skills that any class can train — unlike weapon skills they aren't tied to a class identity, so there's a single flat MEDIUM rate for all three rather than a per-class table, and (like Arcane Level) they start at skill 0: nobody begins already good at swinging a pickaxe. They advance through the same use-based formula above, one successful gather = one action.

Each profession needs a **tool** carried in the backpack (a pickaxe for Mining, a hatchet for Woodcutting, a rod for Fishing — Fishing additionally consumes one unit of **bait** per cast, tiered the same way) — tools are carried, not equipped; there's no dedicated tool slot yet alongside the 10 gear slots in Section 26. Gathering nodes (ore veins, trees, fishing spots) come in **tiers**, and two independent things gate a successful gather:

- **Skill level gates whether a node can be attempted at all.** A tier-2 node ("a harder mine") refuses a too-low skill level outright — this is the "better mining level → harder mine" half of the design.
- **Tool tier (and bait tier, for Fishing) gates whether the attempt then succeeds.** A tier-1 pickaxe simply cannot break a tier-2 vein, regardless of skill level — this is the "better pickaxe → better stone" half. For Fishing, the *lower* of rod tier and bait tier caps which fish tier can be landed, so both matter.

Gathering itself is **deterministic** once both gates pass — no roll, no chance to fail or come up empty — RNG stays reserved for monster loot (Section 12), not for professions. What a higher skill level actually buys is speed: each gather sets a short per-profession cooldown (`BaseSeconds / (1 + SkillLevel / 100)`, floored at 0.6s) before the next attempt, so "higher Fishing level → faster fishing" is real without needing a random catch-fail mechanic. A depleted node respawns after a fixed delay, same shape as a monster corpse expiring (Section 12) or a monster's own respawn timer (Section 11).

**Current build status:** two tiers per profession are in and playable — a tier-1 node anyone can start on (Copper vein, Birch tree, a shallow fishing spot) and a tier-2 node needing both level 15 and the better tool (Iron vein, Oak tree, a deep spot). Every class starts with a basic tier-1 toolkit (rusty pickaxe/hatchet, a simple rod, 5 earthworms) so gathering is reachable from minute one — there's no general-goods shop yet (Section 32) to buy tiered tools/bait from, so tier-2 gear is debug/loot-only for now. Fish also double as food (Section 6) — a nice free synergy, since they were always going to be edible. What to actually *do* with ore/logs (smithing, carpentry — a full crafting system) is intentionally still undecided, per the original ask: gather first, decide the crafting sinks later.

---

## 6. Combat Resource Systems

Each class's resource reinforces its identity and creates a distinct moment-to-moment decision loop.

| Class | Resource | Name | Regen model | Design intent |
|---|---|---|---|---|
| Knight | Rage-like | **Fervor** | Builds from *dealing and taking* melee damage (0 regen when idle); decays slowly out of combat | Rewards staying in the fight; Knight "runs out of gas" if it disengages, encouraging the tank to hold the frontline |
| Archer | Ammo + Focus | **Quiver (ammo) + Focus (energy)** | Quiver depletes 1 per shot, restocked at NPCs/loot/crafting; Focus regenerates passively at a flat rate, faster when standing still ("steady aim") | Physical ammo creates a real logistics/economy sink; Focus rewards positioning and patience over kiting-and-mashing |
| Mage | Mana | **Mana** | Passive flat regen, boosted by gear (`+regen`), no combat interaction | Classic caster resource-management: burst now vs. sustain later |
| Druid | Mana | **Mana** (same pool type as Mage, different spell costs) | Same as Mage, but with a self-buff ("Meditative Focus") trading movement speed for +200% regen | Encourages the Druid's support playstyle: hang back, meditate between heal windows |
| Assassin | Momentum | **Momentum** | Builds only from landing hits while unseen/flanking or from crits; decays fast out of combat | Rewards aggressive, correct opening — an Assassin who whiffs the opener has nothing to burst with |

Formulas:
- Mana/Focus passive regen: `RegenPerSecond = BaseRegen × (1 + ArcaneLevel/150)` for casters, flat `BaseRegen` for Archer Focus — **only while Fed** (see Satiety below).
- Fervor/Momentum generation: `+GainPerHit = 8 + (WeaponSkill/20)`, decaying at `-5/second` once out of combat for 4+ seconds. Unaffected by Satiety — they were never passive regen to begin with, so there's nothing for hunger to gate.

### What can go wrong
Resource systems that are *too* generous erase the "resource management" skill-expression pillar (Section 27); too punishing and the class feels unplayable solo. Both Fervor and Momentum intentionally **cannot be potion-restored** (unlike Mana, which has potions) — they must be earned in the fight itself, preserving the "burst is a reward for good play" identity for Knight/Assassin.

### Satiety, HP Regeneration & Poison

**Why:** passive regeneration needed a cost, or "wait it out, you'll heal for free" trivializes both potions and the corpse/temple risk in Sections 12 and 20. Tying it to food gives the world something to forage for and makes "did you eat?" a real, slightly absurd, and very old-school question to ask before a hunting trip — realistic even for a level-300 legend, deliberately.

**How it works:**
- Every character has **Satiety**, a countdown timer (seconds of "Fed" remaining), capped at **60 minutes**. It only ever decreases in real time while playing; it does not regenerate on its own — only food refills it.
- **HP regenerates passively, for every class, only while Fed:** `HpRegenPerTick = round(MaxHP × 0.0025)`, applied every **2 seconds** — a full heal from empty takes roughly 6–7 minutes of standing around fed, which is meant to matter (worth doing between fights, not fast enough to replace careful play or potions mid-fight).
- **Mana/Focus regen (Archer, Mage, Druid only, per the formulas above) also requires being Fed** — going hungry doesn't just stop healing, it stops mana too. Fervor and Momentum don't care either way, per above.
- **Food** is eaten from the backpack (one item at a time, from the inventory screen) and adds its own Satiety value, up to the 60-minute cap — extra food beyond the cap is simply wasted, so there's no benefit to hoarding and binge-eating before a trip. Sources: **raw meat** from beasts (an immediate, obvious drop off Bramble Wolves and Ironhide Boars) now; **foraged fruit and berries** from trees and bushes in the world are planned but depend on the gathering-node system (a future addition to Section 16 — trees are currently decorative only).
- **Some food is poisonous**, and eating it is a real, foreseeable risk rather than a random chance on safe food — a Poison Berry always poisons whoever eats it, in exchange for filling them up a little. Poison deals `PoisonDamagePerTick` every **2 seconds** for a set number of ticks (baseline: **1 damage / tick for 10 ticks = 20 seconds** for a common poisonous berry); eating more poisonous food while already poisoned **extends the remaining duration** and raises the tick damage to the worst of the sources involved, rather than resetting or simply stacking unboundedly. **HP regen is suppressed entirely while poisoned** — you cannot out-heal poison by being fed at the same time.

### What can go wrong
A hunger mechanic that's too punishing (draining fast, hard-to-find food) reads as busywork, not depth; the 60-minute cap and easy meat supply off the starter monster roster are tuned so staying fed is a light, background task during normal hunting, not a second job. Poison needs to stay a **visible, opt-in** risk (never a hidden chance on food that looks safe) or it just feels like bad luck rather than a decision.

### How it scales
Satiety and poison are two numbers and a countdown per character, ticked locally client-side-predicted / server-authoritative same as HP — no per-monster or per-item server cost beyond the food item's own two or three static fields.

---

## 7. Movement Speed Formula

### Why
Level should visibly, satisfyingly make the character *faster* over time (a classic old-school MMORPG hallmark), but uncontrolled linear scaling eventually makes veteran characters nearly impossible to hit or to visually track in PvP, and breaks camera-follow behavior. We need smooth growth with a **hard asymptotic ceiling**.

### How it works

```
MovementSpeed(L) = BaseSpeed + SpeedCap × (1 − e^(−L / DecayConstant))
```

With `BaseSpeed = 100`, `SpeedCap = 150`, `DecayConstant = 120`:

```
MovementSpeed(L) = 100 + 150 × (1 − e^(−L/120))
```

| Level | Speed | % of base |
|---|---|---|
| 1 | 101.2 | 101% |
| 10 | 111.5 | 112% |
| 25 | 128.1 | 128% |
| 50 | 151.1 | 151% |
| 75 | 169.6 | 170% |
| 100 | 184.8 | 185% |
| 150 | 205.4 | 205% |
| 200 | 218.4 | 218% |
| 300 | 232.7 | 233% |
| →∞ | 250 | 250% (asymptote, never reached) |

Equipment, mount, and buff bonuses apply as **additional additive percentage bonuses on top of this curve**, but the final value is always hard-clamped:

```
FinalSpeed = min(MovementSpeed(L) × (1 + GearBonus% + MountBonus% + BuffBonus%), AbsoluteSpeedCap)
```

`AbsoluteSpeedCap = 400` (i.e., a fully decked out, mounted, buffed level-300 character is capped at 4× the level-1 base walking speed) — this hard ceiling is the actual guarantee that no character ever becomes untargetable, regardless of how many stacking speed sources are introduced over the game's lifetime.

### What problem it solves
Gives every level-up a small, felt reward (you are perceptibly quicker) while the exponential-decay shape means the *marginal* gain shrinks every level — by level 150 an extra level barely moves the needle, which is exactly the diminishing-returns philosophy applied to a stat outside of combat power.

### What can go wrong
Speed differentials between very-low and very-high level characters affect open-world PvP fairness (a level 300 can simply outrun/catch anything below level ~150). This is treated as an intentional PvP lever (Section 21's level-difference PK penalties already discourage extreme cross-level ganking economically), not a bug, but must be watch-listed during playtesting.

### How it scales
Pure function of level + summed equipment/buff percentages, evaluated client-predicted and server-authoritative per movement tick — O(1) per entity, no lookup tables, trivially supports thousands of concurrently moving entities per world shard.

---

## 8. Combat, Targeting & Abilities

### Targeting
- **Tap** an enemy silhouette to select it (highlighted outline). Selection persists until it dies, leaves range, or the player taps another target/empty ground.
- Basic attack (bottom-right button) always fires at the current selection if in range; if no selection, tapping the button auto-selects the nearest valid hostile in range (assist-target).
- Abilities and offensive runes default to the current selection; **dragging** a rune or a "skill-shot" ability toward a different target/location overrides the current selection for that single use only (Section 9).
- Ground-targeted AoE abilities show a placement reticle on drag; releasing confirms.

### Ability kit shape (per class, per Section 30 MVP)
Each class ships with **10 abilities total across two switchable 5-ability bars** ("Loadout A / Loadout B"), a third bar unlocked later account-wide at a mid-game milestone (e.g., level 60) for 15 total. Switching loadouts is instant but has a short shared lockout (2s) to prevent mid-fight ability-double-dipping via rapid switching.

Ability costs draw from the class resource (Section 6); cooldowns range 4–90s depending on power. No ability is a flat "biggest number, spam on cooldown" — high-value abilities key off *combo state* (e.g., Assassin's finisher requires Momentum ≥ threshold; Knight's taunt-mitigation cooldown is short but Fervor-gated; Druid's group heal has a long cooldown specifically to force triage decisions rather than constant topping-off).

**Current build status: Loadout A is real and playable for all five classes; Loadout B is a working, switchable placeholder with no abilities in it yet** — the toggle itself (button, instant switch, per-slot UI) is fully wired, it just has nothing to show until a second five are designed. Every ability composes from a small, shared set of effect fields (damage, an optional AoE radius around the target, a stun or slow duration, a self-heal, a self-buff to attack or armor, or a short dash) rather than needing bespoke code per ability — this is what keeps 25 abilities maintainable as a single data table instead of 25 special cases. Loadout A:

| Class | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Knight | Shield Bash (dmg+stun) | Cleave (AoE dmg) | Fortify (armor buff) | Second Wind (self-heal) | Warcry (attack buff) |
| Archer | Aimed Shot (big single dmg) | Multishot (AoE dmg) | Crippling Shot (dmg+slow) | Evasive Roll (dash away) | Focus Aim (attack buff) |
| Mage | Firebolt (single dmg) | Fireball (AoE dmg) | Frost Nova (AoE dmg+stun) | Arcane Shield (armor buff) | Blink (dash to target) |
| Druid | Wrath (single dmg) | Bramble Growth (AoE dmg+slow) | Thorn Snare (dmg+stun) | Regrowth (self-heal) | Verdant Ward (armor buff) |
| Assassin | Backstab (biggest single dmg) | Shadow Step (dash to target) | Fan of Knives (AoE dmg) | Crippling Strike (dmg+slow) | Adrenaline (attack buff) |

A damage-dealing cast trains the class's primary skill exactly like a basic-attack hit does (Section 5) — an ability is still a "successful action," not a separate progression track.

---

## 9. Rune System

### Why
Runes let *any* character use powerful effects gated by **skill investment (Arcane Level), not class**, which (a) rewards players who diversify their Arcane Level investment regardless of primary role, (b) creates a shared, tradeable, craftable item category (runes are physical consumable items, stackable, sellable on the market) that fuels the player economy, and (c) gives support/utility tools (healing, cleansing) to classes that wouldn't otherwise have them (e.g., a Knight who trained a little Arcane Level can carry emergency Mending Runes).

### How it works
Runes are drawn from an **upper-screen rune tray** and used via **drag-to-target**:
- Drag onto an enemy (or the current selection, if flicked rather than dragged onto a specific tile) → offensive rune fires at that target.
- Drag onto self or an ally → beneficial rune (healing, cleansing, buffs) applies to that target.
- Drag onto open ground → area/utility runes (e.g., a ground-targeted burst) land at that tile.
- If an enemy is already selected and the rune is offensive, a **single tap** on the rune icon (rather than a full drag) auto-fires at the current selection — full drag always lets the player override the target manually, satisfying the requirement that manual targeting takes priority when used.

Each rune has a **Required Arcane Level** and no class restriction:

| Rune | Required Arcane Level | Effect |
|---|---|---|
| Mending Rune | 15 | Small single-target heal |
| Emberburst Rune | 20 | Fire AoE damage |
| Frostbind Rune | 25 | Single-target damage + slow |
| Cleansing Rune | 30 | Removes one negative status |
| Greater Mending Rune | 45 | Large single-target heal |
| Stormcall Rune | 60 | Powerful chain-lightning AoE |
| Greater Emberburst Rune | 60 | Heavy fire AoE, longer cooldown-equivalent (recharge item cost) |
| Warding Rune | 70 | Temporary damage shield on target |

Runes are **crafted or bought**, each "charge" is consumed on use (a physical inventory item, stacking up to 100 per slot), reinforcing the economy (reagent gathering, crafting professions, market trading) rather than being a free cooldown-only ability.

### What problem it solves
Decouples "who can use powerful effect X" from "which of 5 boxes did you pick at character creation," which lets the itemized economy (crafting, trading runes) matter, and gives every class a build-around reason to invest a *little* into Arcane Level even if it's VERY SLOW for them (Section 5) — a dedicated Knight who slowly reaches Arcane 30 unlocks emergency self-cleanse, a real, felt long-term goal.

### What can go wrong
Because runes are class-agnostic, a min-maxed "Mage who also trained Wardcraft" or "Knight who grinds Arcane Level" could emerge as an optimal hybrid that erodes class identity. Mitigation: Arcane Level's off-class Rate (VERY SLOW = 3.0×, Section 5) makes meaningful rune access for a Knight a genuine multi-month-plus investment — a deliberate, earned hybridization, not a free lunch.

### How it scales
Rune usage is a simple inventory-decrement + server-side requirement check + standard ability-effect pipeline — no different computationally from a class ability, so it adds no extra server complexity at scale.

---

## 10. Mobile Combat UI

Screen layout (portrait or landscape, but landscape/tablet is the primary target per the camera requirements):

- **Bottom-left:** virtual joystick (appears where thumb touches down, "floating joystick" convention) for movement.
- **Bottom-right:** large primary/basic-attack button, ringed by **5 ability buttons** in an arc (the active loadout). A small toggle above/beside the ring switches Loadout A / B (/ C later).
- **Bottom-center:** consumables row — Health potion, Resource potion (mana/ammo-restock/etc.), and 1–2 free slots for class-specific or quest consumables.
- **Top-center strip:** rune tray (scrollable/expandable), drag-out-and-release targeting as described in Section 9.
- **Top-left:** player HP/resource bars, level, active status icons.
- **Top-right:** minimap with its own **+ / − zoom buttons** (scales how much of the character's *already-discovered* map, Section 16, is shown — never the 3D combat camera), party frames appear left-of-center when in a party.

All primary combat actions must be reachable by a right-hand thumb without the hand shifting grip, given the joystick is left-thumb-anchored — a standard mobile-MOBA ergonomic constraint carried over deliberately (this is the one place we explicitly borrow *control philosophy*, not any asset or name, from modern mobile MOBAs, exactly as scoped by the brief).

---

## 11. Monster Architecture (No Monster Levels)

### Why
A creature's danger should come from **what it actually does**, not a level-scaling multiplier slapped on a shared template. This keeps the world legible (a Bramble Wolf is *always* a Bramble Wolf, anywhere, at any character level) and forces players to learn creatures by their real behavior rather than by reading a number.

### How it works
Every monster is a **data-defined entity** with no "monster level" field at all. Definition schema:

```
Monster {
  id, displayName,
  hp, armor,
  resistances: { physical, fire, ice, energy, earth, holy },
  damage: { min, max, type },
  attackSpeed, movementSpeed, attackRange, detectionRange,
  aggression: [Passive | Defensive | Aggressive | Territorial],
  abilities: [ability refs with their own cooldowns/telegraphs],
  aiBehavior: [Wanderer | Guard | Pack | Ambusher | Caster | Fleeing-at-low-HP | ...],
  experienceReward,
  lootTable (Section 12),
  respawn: { timeSeconds, maxConcurrent, spawnArea }
}
```

Difficulty emerges from the *combination* of these fields plus the environment (a narrow corridor full of Ambusher-type monsters is dangerous regardless of any single creature's raw stats). Example roster for the MVP hunting grounds:

| Monster | HP | Dmg | Behavior | XP | Notes |
|---|---|---|---|---|---|
| Mudclaw Grub | 20 | 2–4 | Passive, flees | 4 | Tutorial fodder |
| Bramble Wolf | 45 | 5–9 | Aggressive, Pack (calls 1–2 allies) | 14 | Early pack-tactics lesson |
| Ashfen Goblin | 60 | 6–11 | Aggressive, occasionally casts a weak fire bolt | 20 | Introduces "monster with a spell" |
| Ironhide Boar | 90 | 10–16 | Territorial, charges | 28 | Punishes careless positioning |
| Marsh Serpent | 70 | 8–14 (poison DoT) | Ambusher (submerged until triggered) | 26 | Terrain-based danger |
| Bog Orc Reaver | 140 | 14–22 | Aggressive, Pack, has a knockback | 55 | Mid hunting-ground staple |
| Skitterling Swarm | 30 each, spawns in 4s | 3–6 each | Aggressive swarm | 10 each | AoE-reward encounter |
| Cinder Elemental | 220 | 18–30 fire | Defensive, high fire resist, weak to ice | 95 | First "know your elements" wall |
| Hollow Wraith | 260 | 20–34 energy, life-drain | Aggressive, Fleeing-at-low-HP | 130 | Dungeon elite |
| **Sunken Barrow Guardian (boss)** | 4,000 | 40–70 + AoE slam | Territorial, multi-phase abilities | 2,200 | MVP's dungeon boss, party-recommended |

### What problem it solves
Avoids the classic MMORPG trap of "monster level = character level + N" scaling that makes the *world itself* feel meaningless (nothing is ever truly weak or truly a wall — everything auto-scales to "fair"). Here, a returning level-200 character genuinely trivializes the Hollow Wilds and genuinely still respects the Sunken Barrow Guardian until properly geared/partied — exactly the old-school "the world has real, fixed danger" feeling.

### What can go wrong
Without level-relative scaling, content can go "stale" — zones that were dangerous at launch become permanently trivial as the average player level rises, which risks emptying early zones. Mitigation: low-level zones are kept relevant via (a) being the efficient farming ground for *specific* crafting materials/loot regardless of character level (Section 13's "no universal best monster" philosophy), and (b) new player influx constantly repopulating them — this is treated as an accepted, intentional trade-off of the no-monster-levels philosophy, not a flaw to engineer away.

### How it scales
Monster definitions are static data (designer-authored JSON/DB rows), AI behavior runs as simple finite-state logic per instance — no per-player scaling computation needed at all (a monster's stats don't change based on who's nearby), which is *cheaper* server-side than a level-scaling system and trivially supports large concurrent populations sharing the same spawn.

---

## 12. Loot Table & Rarity System

### Why
Loot must feel *logical* (a wolf drops wolf things) and must create real economic and hunting-ground differentiation (Section 13) — some monsters are worth fighting for XP, others for loot, rarely both.

### How it works
Each monster's loot table is a list of entries, each with:

```
LootEntry {
  itemId,
  rarityTier: [Guaranteed | Common | Uncommon | Rare | VeryRare | UltraRare | QuestItem | BossExclusive],
  dropChance (0–1),
  quantityRange: [min, max],
  conditions?: (e.g. "only if killed by fire damage", "only during event X"),
  modifierRoll?: (for gear drops — an item may roll a small random affix)
}
```

Standard drop-chance bands (tunable per-monster but standardized so players can learn the system):

| Tier | Typical chance | Example |
|---|---|---|
| Guaranteed | 100% | Meat/hide from any beast |
| Common | 25–45% | Basic crafting material |
| Uncommon | 8–20% | Better crafting material, small coin bonus |
| Rare | 1–5% | Named crafting component, minor equipment |
| Very Rare | 0.2–1% | Strong equipment piece |
| Ultra Rare | <0.1% | Signature/unique-ish item, chase item |
| Quest Item | Guaranteed while quest active, else 0% | Never drops outside its quest |
| Boss-Exclusive | Boss-only pool, weighted | Best-in-slot gear pieces |

Example — **Bramble Wolf**:

| Item | Rarity | Chance | Qty |
|---|---|---|---|
| Wolf Pelt | Common | 40% | 1 |
| Wolf Fang | Common | 30% | 1–2 |
| Raw Wolf Meat | Guaranteed | 100% | 1 |
| Sharpened Claw | Uncommon | 12% | 1 |
| Alpha's Fang (crafting reagent, rare) | Rare | 2% | 1 |

Example — **Sunken Barrow Guardian (boss)**:

| Item | Rarity | Chance |
|---|---|---|
| Barrow-forged Blade (weapon) | Boss-Exclusive | 15% |
| Guardian's Warding Sigil (accessory) | Boss-Exclusive | 8% |
| Sunken Crown Fragment (quest item, guild quest) | Quest Item | 100% while quest active |
| Large Glint Pouch | Guaranteed | 100% |

### Monster corpses & contested looting
A kill does **not** hand loot straight to the killer. Experience is awarded immediately (that part is never contested — it's tied to landing the kill, not to what happens next), but gold and every rolled item stay sealed inside the monster's **corpse**, which drops at the death location and must be physically opened. There is deliberately **no ownership window**: whichever character reaches the corpse and opens it first gets everything inside, regardless of who dealt the damage — "kto pierwszy, ten lepszy." A corpse decays after a fixed time whether or not it was ever opened. This is a smaller, more frequent echo of the player-corpse looting tension in Section 20, and it's exactly the kind of old-school, world-feels-real friction the game is built around: racing a party member (or a stranger) to a kill is a normal, expected part of hunting, not an edge case to design away.

Opening a corpse is not a single action that vacuums everything into the backpack — it reveals the corpse's contents (gold is collected automatically on open, since currency is weightless; items are not), and **each item must be individually selected** to move it into the backpack, checked against Carry Capacity (Section 2.5) at the moment it's taken. An item left behind stays in the corpse, visible and takeable by anyone, until the corpse decays — so a character that's full has to make a real choice about what's worth the trip back rather than being blocked outright, and a second player can still pick up whatever the first left behind.

### What problem it solves
Thematic consistency makes the world feel authored rather than randomly generated, and the tiered-chance system gives designers one shared vocabulary/tooling to author hundreds of monsters quickly and consistently, while still allowing per-monster tuning of *which* tiers matter (e.g., a "loot monster" might have unusually generous Rare-tier odds despite modest XP).

### What can go wrong
Open, no-priority looting on a rare/valuable spawn invites **corpse-sniping** — someone who did none of the work grabs the loot the instant it drops. This is an accepted, intentional cost of the design (Section 13 already treats rare-spawn camping as a legitimate but contested hunting strategy), not a bug to patch with an ownership window; players are expected to react by fighting in the open where they can defend the kill, partying up before attempting a contested spawn, or simply accepting the risk as part of that hunting ground's danger. The one thing that *is* mitigated is indefinite denial: a fixed corpse-decay timer means a spawn point is never permanently locked out of the loot pool just because nobody has opened a given corpse yet.

### How it scales
Loot rolls are O(1) per kill (iterate a short static list, roll once per entry) — negligible CPU cost even at thousands of simultaneous kills per second server-wide.

---

## 13. Hunting / EXP Design

Hunting is designed around **trade-offs, not a single optimal answer**:

- **High XP, poor loot:** e.g., Skitterling Swarms — fast, safe, good XP/hour, almost nothing sellable.
- **Low XP, valuable loot:** e.g., Marsh Serpents in the deep bog — modest XP but a real shot at a valuable poison-gland crafting reagent.
- **High XP, extreme danger:** e.g., Hollow Wraiths in the Sunken Barrow — excellent XP but life-drain + flee-and-reset mechanics punish undergeared solo attempts.
- **Rare-item opportunity hunting:** camping a boss/elite spawn point for its exclusive table, accepting low XP/hour in exchange for shot at a chase item.
- **Party-oriented rewards:** pack monsters (Bramble Wolves, Bog Orc Reavers) and the Barrow Guardian boss are tuned so a coordinated 2–4 person party clears them dramatically faster (and safer) than the sum of solo efforts, explicitly rewarding grouping without *requiring* it for normal content.

There is deliberately no single monster that wins on every axis (XP, loot value, safety, speed) — every hunting ground is a legitimate choice depending on the player's current goal (leveling vs. gearing vs. gold-farming vs. risk tolerance).

---

## 14. Party System & Shared XP Formula

### Why
Grouping should be attractive for content, social play, and safety — but must not become a vector for high-level characters to trivially power-level low-level alts/friends, which would gut the slow-progression pillar.

### How it works

**Eligibility:** two characters can share XP from a kill only if their level difference is within **25% of the higher character's level**:

```
|L_i − L_ref| / L_ref ≤ 0.25
```

where `L_ref` is the highest level among the party members actively contributing to/receiving credit for that specific kill. (Example from the brief: a level-100 character can share with levels 75–125.)

**Within the allowed range**, each eligible member's individual share of that kill's XP pool is scaled by a smooth exponential falloff based on their percentage distance from `L_ref`:

```
ShareMultiplier(L_i) = 2 ^ ( −20 × |L_i − L_ref| / L_ref )
```

This produces exactly the "halve every additional 5%" behavior requested:

| Level difference from L_ref | ShareMultiplier |
|---|---|
| 0% (same level) | 1.00 (100%) |
| 5% | 0.50 (50%) |
| 10% | 0.25 (25%) |
| 15% | 0.125 |
| 20% | 0.0625 |
| 25% (boundary) | 0.03125 (~3%, negligible) |
| >25% | Not eligible — receives 0 shared XP from that kill (falls back to solo XP rate if they land the killing blow themselves) |

The total XP pool from a kill is the monster's base `experienceReward` multiplied by a modest **party bonus** (`1 + 0.10 × (partySize − 1)`, capped at party size 6) to reward grouping, then that pool is split proportionally by each present member's `ShareMultiplier`, normalized so the multipliers of all *currently contributing* members sum to 1 (i.e., relative weighting, not each member independently getting their full multiplier for free).

**Worked example:** party of a level-100 (`L_ref`) and a level-90 character (10% below) fighting together. Level-90's weight = 0.25, level-100's weight = 1.00. Normalized: level-100 gets 1.00/1.25 = 80% of the pool, level-90 gets 20% — noticeably reduced from an even 50/50 split, but not zero, so the lower-level friend still meaningfully progresses.

### What problem it solves
Prevents "level 300 escorts level 5 through content, level 5 hits level 100 in an afternoon" power-leveling, which would make the entire multi-year leveling curve (Section 4) meaningless for anyone with a well-connected friend, while still letting realistically-close-in-level friends (a very common real case) group up with only a mild, fair penalty.

### What can go wrong
A hard cliff at exactly 25% invites "boundary-riding" exploitation (deliberately staying at 24.9% difference). The smooth exponential *within* the range already makes riding the edge nearly worthless (~3% share), and the outright cutoff beyond 25% removes any incentive to min-max past that point — the curve itself defends the boundary.

### How it scales
Per-kill computation is O(party size) — trivial even for max-size (6-person) parties, computed once per kill event; no persistent state beyond each member's current level (already tracked).

---

## 15. Quest System Architecture

### Why
Classic MMORPG quests reward *player knowledge and exploration*, not UI-following. This is a major differentiator from modern quest-marker MMOs and directly serves the "world feels real" pillar.

### How it works
Quest information is delivered exclusively through **diegetic sources**:
- NPC dialogue (branching, with memory of prior answers/quest state)
- In-world books/journals/notes (readable item objects placed in the world)
- Signs, carvings, environmental storytelling
- Player-to-player knowledge sharing (intentionally not fully explained in any single in-game source — some quests are only solvable by piecing together multiple NPCs across different locations)
- Maps as literal, sometimes-purchasable or lootable items with hand-authored (not GPS-pin) imagery

No quest log auto-marks a map waypoint. The quest log records *text the player has already learned*, as a personal journal, not a pointer.

**Quest types supported:**
- **Solo quests** — single-player narrative/reward loops.
- **Party quests** — require a group (mechanically gated, e.g., a lever puzzle needing simultaneous multi-position activation).
- **Limited-capacity quests** — an instanced or semi-instanced encounter capped at N concurrent participants (e.g., max 4 players inside a specific boss quest room at once; a queue/signup NPC manages entry).
- **Multi-stage quests** — chains with escalating requirements/travel across multiple zones.
- **Hidden quests** — no NPC ever announces "I have a quest for you"; discovered purely by exploration/dialogue triggers/reading.
- **Repeatable quests** — dailies/weeklies for steady gold/material/reputation income (a key economy and habit-formation tool).
- **Boss quests** — narrative gate + mechanical gate to a boss encounter, often party-only.
- **Guild quests** — require guild-level participation/resources (Section 24), rewarding guild-wide progression (territory, guild hall upgrades).

### What problem it solves
Preserves exploration and world-knowledge as genuinely valuable player skills (a veteran player's "I know where the hidden entrance is" is real capital, socially and in guild recruiting), which reinforces long-term retention far better than a checklist UI that trivializes exploration.

### What can go wrong
Undiscoverable-feeling quests frustrate modern mobile audiences used to hand-holding. Mitigation: hidden ≠ unfair — every hidden quest must have *some* discoverable breadcrumb (an NPC mentions a rumor, a book hints at a location) reachable through normal exploration/dialogue, just never a literal waypoint; and casual/onboarding quests (MVP scope) are more overt, with hidden/obscure quests reserved for deeper, optional, veteran-facing content.

### How it scales
Quest state is per-character flags/counters (standard MMORPG quest-state modeling); limited-capacity quests need a lightweight instance/reservation service (a queue + per-attempt instance ID), which is a well-understood scaling pattern (same shape as a dungeon-finder reservation system) and isolated from the main open-world simulation.

**Current build status:** the first solo quest is in and playable end-to-end — Elder Mara offers "Cull the Grubs" (kill 5 Mudclaw Grubs), tracks progress on each kill, and pays out EXP/gold/an item on turn-in. This validates the full per-character quest-state shape (accept → active/progress → readyToTurnIn → completed, never re-offered) that every future quest builds on; party, limited-capacity, multi-stage, hidden, repeatable, boss, and guild quest *types* (this section's list above) are still to come — one working solo quest first, before multiplying the type-count.

---

## 16. World Architecture & Travel

The world is a single persistent, seamless (per shard) open world composed of interconnected regions — no loading-screen "select destination" menu for anything reachable by foot.

- **Regions:** cities (Duskmere, Ravensport), wilderness (Hollow Wilds), dangerous frontier (Bloodmarsh Frontier), dungeons (Sunken Barrow), and later mountains/deserts/islands as content expands, all physically bordering one another.
- **Travel:** overland is on-foot (+ mounts later); inter-island/continent travel uses **ships as physical world objects** — the player walks to a dock, talks to a Ferryman NPC, pays a Glint fare, and a travel sequence (a short, real transit — not an instant cut) carries them to the destination dock. Later game stages introduce faster options (teleportation circles, wizard-cast group teleport spells, rare artifact-based fast travel) but these are always *unlocked, costly, or limited*, never replacing the base experience of a new player's first sea crossing.
- **Persistence:** world state (spawns, guild territory flags, player-placed structures if introduced later, market listings) lives server-side per shard; multiple shards may exist for population/latency reasons, with clear shard identity (no silent server-merges of PvP reputation, since Section 21 depends on it).

**Current build status:** a working two-way Ferryman crossing is in — Brack at the Duskmere-side dock, Rill at the Ravensport-side dock, 10 Glints each way. The prototype's single shared 3D scene stands in for "two docks" (there's no separate loading zone/second map yet — the far dock is a stub point in the same world, per the MVP scope in Section 32), but the player-facing flow already matches the target: walk to the dock, talk to the Ferryman, pay the fare, arrive at the other side. Real inter-region loading/hand-off is a later pass once there's an actual second region to justify it.

### Map discovery (fog of war)
No character starts with the map revealed. The minimap and full-screen map only show terrain the character has physically walked through (or seen from a discovered vantage point) — everywhere else stays blank/fogged, exactly like the "no waypoints, learn the world by exploring it" philosophy already governing quests (Section 15). Discovery is per-character and permanent (revisiting later doesn't re-fog it), stored as a coarse explored-tile grid per region rather than per exact coordinate, so the cost of tracking it stays small even at high player counts. This is also why the minimap's zoom (Section 10) only changes how much of the *already-discovered* map is shown on screen, never reveals undiscovered terrain, and is completely separate from the fixed 3D combat camera — the two solve different problems and neither should compensate for the other.

### What can go wrong
Fully seamless open worlds are the most server/tech-architecture-intensive option (interest management, entity replication, zone hand-off if sharded internally). Mitigation: internally partition the world into server-side "cells" for interest-management purposes (a standard MMO server pattern), invisible to the player, so the *player-facing* experience is seamless even if the backend spatially partitions simulation load.

---

## 17. NPC System

NPCs support: dialogue trees, shops (buy/sell with individually stocked, sometimes limited/restocking inventories), quest-giving/tracking, travel services (Ferryman-type), and general "lore/information" dialogue that exists purely to convey world knowledge (including quest breadcrumbs per Section 15). Dialogue is interactive (player picks from response options, not a single "press to skip" wall of text) — this is the primary delivery mechanism replacing quest markers, so it must feel worth reading, not worth skipping.

**Current build status:** a quest-giver (Elder Mara), a Depot keeper (Orin), and a two-way Ferryman pair are in and playable. NPCs are stationary and get their own context-sensitive **"Rozmawiaj"/"Depozyt" prompt**, deliberately separate from the ATAK/SZUKAJ button, so standing next to one never competes with nearby combat. The general-goods shop (buy/sell) from the MVP scope (Section 32) isn't built yet — dialogue trees today only branch on quest state (offer / in-progress / ready-to-turn-in / already done), not on prior free-form answers.

---

## 18. Depot / Storage

Every city has a **Depot** — a persistent, personal storage vault accessible only inside that city (via a Depot NPC/chest), holding weapons, armor, resources, quest items, loot, and consumables. Storage is unlimited-slots-but-tiered by default capacity with paid/earned expansions (a natural, non-power-affecting monetization/gold-sink lever, Section 25). Depots are **per-city** at launch (each city's depot is a separate stash) with a later "linked depot" unlock (a mid/late-game guild or premium feature) letting players access one shared pool from any city — introduced deliberately late so early-game logistics (deciding what to carry vs. store, per city) remain a meaningful decision.

**Current build status:** interacting with Orin the Keeper opens a two-column Depot screen — backpack contents with a "Wpłać" (deposit) button, and the Depot's own contents with a "Wypłać" (withdraw) button — one item at a time, mirroring how corpse looting already works (Section 12). Withdrawing is still gated on carry capacity like any other pickup; depositing never is, since it's leaving the character's person. Capacity tiers/expansion costs are a later economy pass, not in yet — the MVP Depot is simply unlimited.

---

## 19. Temple & Respawn

Each city has a **Temple** — the assigned respawn point after death (Section 20). Players can change their "home temple" via an NPC (for a cost, to prevent frictionless respawn-hopping). Temples are always inside guard-protected safe zones — no combat is possible within a set radius.

---

## 20. Death & Corpse System

### Why
Death must be *feared but not devastating* — old-school MMORPGs derive enormous tension from real death stakes; modern MMOs derive enormous casual-friendliness from zero-stakes death. Thornreach targets the classic side, with tuned safety nets so the risk stays "tense" rather than "quit-inducing."

### How it works
1. On death, the character is teleported to their assigned Temple (Section 19) with a short debuff (reduced stats/regen for a few minutes — "Shaken" status) but never permanent stat loss.
2. A **corpse** is created at the death location, containing a portion of the deceased's carried (non-equipped, non-protected) inventory.
3. **Protection mechanics** reduce, but never eliminate, loss:
   - Items **equipped** (worn gear) are never lost on a PvE death; only unequipped/backpack-carried items are corpse-droppable.
   - A small guaranteed "keep" allowance (e.g., a fixed number of most-valuable carried items, or a percentage floor) is always protected, softening bad-luck total wipes.
   - A purchasable/earnable **Death Ward** consumable further reduces drop chance/quantity for a limited number of uses — an gold/effort sink that directly answers "protection mechanics that reduce loss without eliminating danger."
4. The corpse persists in the world for a limited time (e.g., 15–30 minutes, scaling somewhat with the value of its contents to avoid instant-decay ninja-looting on rich corpses) during which:
   - The original owner (or their party, with owner-priority for a short initial window) can return and reclaim everything not yet taken.
   - After the priority window, **any other player** may loot the corpse — including in PvP contexts, this is a deliberate source of player-driven tension/stories (Section 21).
5. PvP deaths carry a *harsher* corpse-drop profile than PvE deaths by default (more of the backpack is droppable), specifically to make player killing carry real weight and consequence, distinct from a monster death.

### What problem it solves
Recreates the classic "corpse run," tension, and stories ("I got my gear back just in time," "someone looted my corpse and I never forgave them") that defines old-school MMORPG memory-making, while the layered protections (equipped-gear-safe, guaranteed floor, Death Ward item) prevent the single worst old-school failure mode: a new/casual player rage-quitting after losing everything to one bad pull.

### What can go wrong
Corpse-camping (killing a player repeatedly to deny corpse recovery) is a classic griefing vector. Mitigation ties into the PK system (Section 21): repeatedly killing the same player/corpse-camping accrues escalating "criminal" consequences, making it costly for the aggressor, not just annoying for the victim.

### How it scales
Corpses are lightweight, timed world objects (spawn → timer → despawn/looted) — a well-understood, cheap pattern; no different in server cost from any other timed loot container, and volume is naturally bounded by death rate (which is self-limiting — players avoid dying often).

---

## 21. PvP / PK System

### Why
Open-world, unscripted player conflict is a defining pillar of the old-school MMORPG fantasy — queue-based arenas are a different game entirely and are explicitly out of scope for the core loop.

### How it works
- **Open-world PvP** is possible anywhere outside declared safe zones (cities, temples, starting wilderness up to a level/skill threshold). No queue, no matchmaking — you meet who you meet.
- **Criminal/reputation status:** attacking a player who has not recently attacked/flagged against you marks you **Unjustified** (a visible, server-tracked status). Accumulating Unjustified kills raises your **Murder Count** and eventually marks you **Wanted** (visible name-tag/marker, bounty-eligible, guards in safe zones become hostile to you, harsher death penalties apply to *you* specifically while Wanted).
- **Skirmish/self-defense exemption:** retaliating against someone who attacked you first within a short window does not flag you as an aggressor.
- **Bounty system:** any player may place a Glint bounty on a Wanted player's head, claimable by whoever kills them next (a player-driven "wanted poster" economy loop).
- **Guild wars:** guild leadership can formally declare war on another guild, which mutually suspends the Unjustified penalty between the two guilds' members for the war's duration — organized conflict without the criminal-status friction, matching real old-school guild-war dynamics.
- **Safe zones:** cities/temples and select sanctuaries are always no-PvP, guard-enforced; most of the wilderness is not.
- **PvP protection for new characters:** a time/level-limited "newcomer" flag (e.g., first ~2 weeks or below a low level threshold) prevents being attacked by (but does not prevent attacking, if they choose) far-higher-level players outside of guild wars, curbing predatory new-player griefing without eliminating open-world PvP as a whole.

### What problem it solves
Creates emergent, player-authored conflict and stories (rivalries, bounty hunts, guild vendettas) that scripted matchmaking cannot produce, while the criminal-status/consequence layer keeps unrestricted ganking from becoming the *only* viable playstyle and driving away the hunting/questing majority.

### What can go wrong
Any open-world PK system risks a "safe zone problem" (predators camping just outside town) or a "toxic minority ruins the game for the majority" failure mode seen in many old-school MMOs. Mitigation: the escalating Wanted consequences (guard hostility, harsher death penalties while Wanted, bounty target) are specifically tuned to make *serial* unjustified killing an active liability, not a free playstyle — occasional PvP conflict stays cheap, sustained griefing stays expensive.

### How it scales
Reputation/Murder Count/Wanted status are simple per-character counters with decay-over-time rules; guild-war state is a small relation between two guild IDs. None of this requires anything beyond standard database state — no matchmaking service needed since PvP is spatial/open-world, not queued.

---

## 22. Find-Player Spell

A navigation spell (name: **Seeking Rune** or a Druid/Mage-accessible spell, Arcane Level gated) that lets a player search for a named character:

- Input: target character name.
- Output: **coarse directional text only** — one of `North, North-East, East, South-East, South, South-West, West, North-West, Nearby, Very Far` (and a "Not Found"/"target is warded" result for offline or protected targets) — never coordinates, never a map ping.
- Costs mana + has a cooldown (e.g., 60–120s) + has an Arcane Level requirement, consistent with the rune-requirement philosophy (Section 9) even though this is a learned spell rather than a consumable rune.
- Deliberately preserves uncertainty — direction only, no distance-to-meter precision, no persistent tracking — the player must still physically travel and search, keeping "the hunt for a person" a real, skill-and-effort-based activity (useful for both cooperative reunions and PvP bounty hunting per Section 21).

---

## 23. Social Systems

Friends list (with online status), private messaging, party (Section 14), guilds (Section 24), guild chat, a public/local chat channel (proximity-based, heard only by nearby characters — reinforcing "the world is real," not a global firehose), player inspection (view another character's visible equipment/level, not full skill sheet, to preserve some mystery/inspection-as-social-ritual), direct trading (a secure two-player trade window, item-for-item/gold, both must confirm), player search (find a guild/character by name in a directory), ignore/block, and leaderboards (level, guild territory, PvP renown, etc., server/shard-scoped).

---

## 24. Guilds

Guild creation (gold + minimum member cost, a gold sink), internal rank hierarchy (Leader, Officer ranks with configurable permissions, Member), guild chat, a **guild bank** (shared, permission-gated storage — separate from personal Depot, Section 18), guild quests (Section 15), guild wars (Section 21), guild alliances (mutual non-aggression/cooperation flag between guilds), and a guild progression track (guild XP earned from member activity/guild quests, unlocking a guild hall, bank capacity, and cosmetic/utility perks — never raw combat power, to avoid guild size/age becoming a hard power multiplier). **Territory control** (guild-held zones granting resource/economic bonuses, contestable via structured guild-war windows) is an explicit later-game system, not MVP.

---

## 25. Economy

Player-driven economy built on: Glints/Slivers currency, NPC shops (fixed-price sinks/sources for basics), player-to-player trading, a **market/auction house** (list an item for N Glints, browsable/searchable, a small listing/sale fee as a gold sink), crafting (turns loot/gathered materials into gear/consumables — a major use for the loot system's Common/Uncommon tiers), repairs and equipment upgrades (gold + material sinks that scale with gear power, keeping high-end gear maintenance meaningful), and deliberate **item and gold sinks**: Depot expansion costs, guild creation/upkeep costs, market fees, repair costs, Death Ward consumables, travel fares, home-temple changes. These sinks are sized, at design time, to roughly offset the primary gold *sources* (monster coin drops, quest rewards, sold loot) at a steady-state ratio tuned via live simulation before launch and monitored (via server-side currency-sink/source telemetry) continuously post-launch to control long-term inflation across years of play — this is a live-ops responsibility, not a one-time formula, and the design must expose the necessary sink "dials" (fee %, repair cost curve) as tunable server config, not hardcoded constants.

---

## 26. Item System

### Equipment slots

Ten slots, every one of them a real, separately-equipped item — no shared "accessory" catch-all:

| Slot | Notes |
|---|---|
| Helmet | |
| Armor (chest) | |
| Legs | |
| Boots | |
| Gloves | |
| Weapon | Interacts directly with the trained weapon skill (Section 5) — a weapon has a *type* (Blade/Axe/Bludgeon/Bow-or-Crossbow/Talon/none-for-casters), and damage output scales with the matching skill, so gear and skill investment are always coupled, never independent axes. |
| Shield | Off-hand; feeds Wardcraft (Section 5). |
| **Ammunition / Reagent** | One shared slot type, filled differently by class: **arrows or crossbow bolts** for the Archer, **arcane essence** for the Mage and Druid. Knight and Assassin have no item that fits it and simply leave it empty — it's not hidden for them, there's just nothing to put there. This is the physical form of the Archer's Quiver and the casters' extra reagent cost (Section 6); real per-shot/per-cast depletion is a combat-resource feature to wire in alongside the ability system, not yet active in the current build. |
| Amulet | The slot most likely to carry a resource bonus (max Mana/Fervor/Focus/Momentum) rather than armor. |
| **Cape** | **Locked until level 10** ("Proven," Section 29) — the slot itself doesn't appear on the character sheet before then, not just the items for it. A deliberate small reward tied to that first milestone, the same way the account-wide third ability loadout (Section 10) is a later unlock rather than a day-one default. |

Some gear is class-restricted where it makes sense (arrows and essence pouches only fit their intended classes) — this is the one place items *do* gate by class, unlike runes (Section 9), because a quiver is a physical container tied to a fighting style, not a magic-requirement-gated consumable.

### Item properties

Weapons interact directly with the character's trained weapon skill (Section 5) — a weapon has a *type* (Blade/Axe/Bludgeon/Bow-or-Crossbow/Talon/none-for-casters), and damage output scales with the matching skill, so gear and skill investment are always coupled, never independent axes. Items carry: level/skill requirements (gating access, not just recommending it), a fixed statline (avoiding excessive per-drop randomization — a "Barrow-forged Blade" always has the same base stats so players can learn and value items by name), a rarity tag (for visual/UI clarity, distinct from the loot-table rarity tiers of Section 12), a small number of possible **modifier slots** (limited, deliberate randomization on drop — e.g., 0–2 minor affixes rolled within a tight, known range, not open-ended stat soup), and durability where it serves a purpose (a slow-decaying stat on high-end gear that creates a repair/maintenance gold sink, not a punishing break-and-lose-forever mechanic).

---

## 27. Combat Philosophy Summary

Combat must reward **positioning** (melee range management, kiting, using terrain/corners against ranged/casters), **timing** (dodging telegraphed AoEs, landing Assassin openers, timing Druid heals through burst windows), **target selection** (focus-firing the right threat in a group fight, protecting a healer), **resource management** (Section 6 — never "free" ability spam), **equipment** (meaningful stat/skill-gated gear, not cosmetic-only), and **character progression** (skills/levels create real, felt power differences over time). It must never degenerate into "press the strongest cooldown available" — enforced structurally by resource gating, combo/state requirements (Momentum, Fervor thresholds), and long, meaningful cooldowns on the highest-impact abilities rather than a flat rotation.

---

## 28. Visual Style & Camera

**Visual target:** stylized chibi-fantasy 3D — small, expressive proportions (larger head, compact body) on every class, painterly hand-painted-look textures, warm saturated lighting, and readable silhouettes per class archetype (Knight's bulk, Mage/Druid's robes, Assassin's hood, Archer's cloak) so a target is identifiable at a glance on a small phone screen. All five launch classes share one body proportion and skeleton, differing only in mesh, texture and silhouette — this is a deliberate production choice, not just an art style: it lets every class and future gear piece reuse the same animation set (walk, basic attack, cast, hit react, death) instead of hand-authoring animations per class. The look is original in every silhouette, palette and ornament (no visual resemblance to Tibia's 2D/2.5D retro aesthetic or to any existing MOBA's or mobile RPG's character designs). The chibi/low-poly-friendly style is also a deliberate mobile-performance choice: lighter geometry and simpler shading than a realistic-3D target, giving real headroom on mid-range phones alongside the higher-end devices used for development.

**Camera:** third-person, player-centered, smooth-follow. **Both the angle and the distance are fixed and identical for every player — there is no player-controlled rotation and no zoom on the 3D camera.** This is a fairness decision, not an oversight: a rotatable or zoomable camera would let a player peek around obstacles, or simply see further across the battlefield, in a way other players standing at the same spot cannot — and an open-world PvP game is full of moments where two players are looking at the very same fight and that gap would matter. A fixed camera also keeps "north on the minimap" and "up on screen" meaning the same thing for everyone, which matters for the Find-Player spell's directional callouts (Section 22) and for describing locations to guildmates in chat. Seeing further is instead something the minimap alone provides, at a fixed, equal cost to every player (Section 10) — never the combat camera. Framing is tuned for wide peripheral visibility around the player at its one fixed distance (reading incoming melee/ranged threats and AoE telegraphs in combat) — a mobile-MOBA-style camera *behavior*, built entirely with original assets and framing choices.

---

## 29. Long-Term Progression Milestones

Both character level and each individual skill treat these as **narratively and mechanically framed achievements** (title unlocks, cosmetic flourishes, guild-hall trophy plaques, leaderboard tiers — never just a silent number tick):

| Level milestone | Framing |
|---|---|
| 10 | "Proven" — leaves newcomer PvP protection eligible range |
| 25 | "Seasoned" — first real gear tier unlocks |
| 50 | "Veteran" — ~1 month of serious play; first major title |
| 75 | "Elder" |
| 100 | "Master" — ~1 year of dedicated play; rare, visible title |
| 150 | "Grandmaster" |
| 200 | "Legend" — multi-year achievement, top-of-leaderboard territory |
| 300+ | "Mythic" tier — open-ended, aspirational, server-first bragging rights |

Skills follow the same milestone-framing philosophy at equivalent skill-level thresholds (e.g., skill 100 in a class's signature weapon is a comparable "Master"-tier achievement to character level 100, per the Section 5 curve).

---

## 30. MVP — Vertical Slice

Goal: prove the full core loop end-to-end with the smallest honest content set — **not** a smaller version of every system, but the *complete* version of a small number of systems.

**Content:**
- 1 city (Duskmere): Temple, Depot, 1 NPC general-goods shop, 1 travel NPC (a working ship route to a placeholder second dock, even if the far side is a small stub area)
- 1 small wilderness area (Hollow Wilds slice)
- 1 dungeon (a small first section of the Sunken Barrow, with 1 boss: the Barrow Guardian, tuned down from the full-game numbers above for solo/duo MVP testing)
- 8–12 monsters (the roster in Section 11's table)
- All 5 classes, each with their resource system and a first-pass 5-ability starter loadout (Loadout A only; Loadout B/switching can be a fast-follow if needed to hit MVP timeline, but is in scope per the brief)

**Systems (full, not stubbed):**
- Leveling (Section 4 formula) and skill progression (Section 5 formula)
- Basic inventory + equipment (a meaningful subset of slots/items, not all eight)
- Combat: basic attack + 5 abilities + targeting (tap-to-select, auto-basic-attack)
- Loot system (Section 12, scoped to the MVP monster roster)
- Potions (health + one resource potion type)
- A small rune set (2–3 runes: one offensive, one Mending, one utility) with drag-to-target
- Basic party + shared XP (Section 14 formula, fully implemented — it's cheap and central)
- Basic PvP (open-world flagging/Unjustified status, no full bounty/guild-war layer yet)
- Death + corpse + recovery (Section 20, full loop)
- 1 hand-authored quest exercising the "no waypoint, NPC + environmental clue" philosophy (Section 15)
- Basic NPC dialogue (branching, at least the shopkeeper + quest-giver + Ferryman)
- Basic ship travel (Section 16, even if the destination is minimal)

**Loop proven:**
`Create character → enter city → leave city → explore → fight monsters → gain XP → level up → get loot → return to city → store loot (Depot) → upgrade equipment → return to world → hunt → party → PvP → die → return to corpse → recover loot → continue progression.`

Everything **not** listed above (guild wars, territory control, bounty boards, linked depots, mounts, third ability loadout, crafting professions, market/auction house, multiple cities/islands, hidden/limited-capacity/guild quests) is explicitly **post-MVP**.

---

## 31. Development Order

1. Finalize game design *(this document)*
2. Finalize progression formulas — Sections 4–5 ✅ (locked pending playtesting)
3. Finalize five classes — Section 2 ✅
4. Finalize skill system — Section 5 ✅
5. Finalize combat system — Sections 6–9, 27 ✅
6. Finalize monster architecture — Section 11 ✅
7. Finalize item architecture — Section 26 ✅
8. Finalize loot tables — Section 12 ✅
9. Finalize player data model (level, XP, skills, resource, inventory, equipment, position, guild/party refs, criminal status) — next technical task
10. Finalize networking architecture (authoritative server, client prediction for movement/targeting, interest-management cell partitioning per Section 16) — next technical task
11. Create one small test map (Hollow Wilds slice)
12. Implement movement (joystick + speed formula, Section 7)
13. Implement camera (Section 28)
14. Implement targeting (Section 8)
15. Implement combat (basic attack + resources, Sections 6, 8)
16. Implement monsters (Section 11 roster + AI behaviors)
17. Implement XP (Section 4)
18. Implement leveling (level-up effects: HP/resource/speed recompute)
19. Implement inventory
20. Implement equipment
21. Implement death/corpse (Section 20)
22. Implement PvP (Section 21, MVP scope)
23. Implement party (Section 14, full shared-XP formula)
24. Implement quests (Section 15, 1 quest)
25. Implement NPCs (Section 17)
26. Implement depot (Section 18)
27. Implement travel (Section 16, ship route)
28. Implement UI (Section 10)
29. Optimize mobile performance
30. Expand the world

No system outside the Section 30 MVP list should be implemented before the MVP loop is fully playable end-to-end.

---

## 32. Risks, Open Questions & Live-Ops Levers

**Open questions for a follow-up design pass (not blocking MVP start):**
- Exact numeric balance of all class abilities (kit design is a separate, focused pass per class).
- Precise crafting-profession list and recipe trees (Section 25/26 depend on it existing, but MVP doesn't require crafting).
- Mount system details (unlock method, speed-formula interaction bounds within the `AbsoluteSpeedCap`).
- Exact newcomer PvP-protection duration/threshold (Section 21) — needs live playtesting data, not a launch-day guess.

**Primary live-ops tuning levers already designed into the systems** (so balancing post-launch never requires a new formula, only a constant change):
- Global XP multiplier (Section 4's leading constant `5`)
- Per-class skill `Rate` table (Section 5)
- Monster `experienceReward` and loot-table chances (Sections 11–12)
- Movement `SpeedCap`/`DecayConstant`/`AbsoluteSpeedCap` (Section 7)
- Party bonus % and the shared-XP exponent constant `20` (Section 14)
- Economy sink costs (repair curve, market fee %, Depot expansion pricing) (Section 25)

**Top risks to watch during playtesting:**
1. XP curve pacing drifting from the "~1 month to level 50" target once real hunting-ground XP/hour is measured — mitigate via the global multiplier lever before touching the formula shape.
2. Class balance (Assassin burst vs. survivability, Knight damage floor) — mitigate via ability-level tuning, not base-stat inflation.
3. Open-world PK griefing pressure on new players — mitigate via newcomer protection window tuning, watched closely in the first weeks of any open beta.
4. Corpse-camping/loot-ninja social friction — mitigate via the owner-priority looting window and Wanted-status escalation.
