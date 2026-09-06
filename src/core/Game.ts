import * as THREE from 'three';
import { Player } from '../entities/Player';
import { Monster } from '../entities/Monster';
import { Corpse } from '../entities/Corpse';
import { InputController } from '../input/InputController';
import { HUD } from '../ui/HUD';
import { LootPanel } from '../ui/LootPanel';
import { InventoryPanel } from '../ui/InventoryPanel';
import { buildWorld, clampToWorld } from '../world/World';
import { MONSTER_DEFS } from '../data/monsters';
import { ABILITIES, CLASS_LOADOUT_A } from '../data/abilities';
import { applyLevelStats, SKILL_NAMES, type ClassId, type SkillId } from '../types';

// No two spots share a monster type — GDD Section 13: different creatures
// should create different hunting strategies, not one best monster.
const MONSTER_SPAWNS: Array<[keyof typeof MONSTER_DEFS, number, number]> = [
  ['mudclawGrub', 4, 3],
  ['mudclawGrub', -6, 2],
  ['brambleWolf', 6, 4],
  ['brambleWolf', -8, 5],
  ['brambleWolf', 10, -6],
  ['ashfenGoblin', -5, -9],
  ['ashfenGoblin', 14, 8],
  ['ironhideBoar', -14, -3],
  ['ironhideBoar', 3, 14],
];

// Fixed for every player — no rotation, no zoom (GDD Section 28). Seeing
// further is the minimap's job (Section 10), never the combat camera's.
const CAMERA_OFFSET = new THREE.Vector3(0, 6.5, -7);

const TARGET_SELECT_RADIUS = 4;

export class Game {
  private readonly scene = new THREE.Scene();
  private readonly camera: THREE.PerspectiveCamera;
  private readonly renderer: THREE.WebGLRenderer;

  private readonly player: Player;
  private readonly monsters: Monster[] = [];
  private readonly corpses: Corpse[] = [];
  private readonly input: InputController;
  private readonly hud: HUD;
  private readonly lootPanel: LootPanel;
  private readonly inventoryPanel: InventoryPanel;

  private clock = new THREE.Clock();
  private targetMonster: Monster | null = null;
  private targetCorpse: Corpse | null = null;
  /** The corpse the loot panel is currently showing, if any (distinct from targetCorpse,
   * which recomputes every frame by proximity and would otherwise yank the panel around). */
  private openedCorpse: Corpse | null = null;
  /** Loadout B is a switchable but currently empty placeholder (GDD Section 10). */
  private currentLoadout: 'A' | 'B' = 'A';

  constructor(root: HTMLElement, canvasHost: HTMLElement, classId: ClassId) {
    this.player = new Player(classId);
    this.scene.background = new THREE.Color(0x8fd0ff);
    this.scene.fog = new THREE.Fog(0x8fd0ff, 20, 55);

    this.camera = new THREE.PerspectiveCamera(
      60,
      window.innerWidth / window.innerHeight,
      0.1,
      200,
    );

    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.shadowMap.enabled = true;
    canvasHost.appendChild(this.renderer.domElement);

    this.setupLighting();
    buildWorld(this.scene);
    this.scene.add(this.player.mesh);

    for (const [type, x, z] of MONSTER_SPAWNS) {
      const monster = new Monster(MONSTER_DEFS[type], new THREE.Vector3(x, 0, z));
      this.monsters.push(monster);
      this.scene.add(monster.mesh);
    }

    this.input = new InputController(root);
    this.hud = new HUD(root);
    this.lootPanel = new LootPanel(root);
    this.inventoryPanel = new InventoryPanel(root);
    this.hud.update(this.player.stats, this.hudDerived());

    root.querySelector('#capacity-btn')!.addEventListener('click', () => this.toggleInventory());

    window.addEventListener('resize', this.onResize);
  }

  private toggleInventory(): void {
    this.inventoryPanel.toggle(
      this.player.stats,
      (itemId) => {
        if (!this.player.equipItem(itemId)) {
          this.hud.showToast('Nie możesz teraz tego założyć');
        }
        this.inventoryPanel.render(this.player.stats);
      },
      (slot) => {
        this.player.unequipItem(slot);
        this.inventoryPanel.render(this.player.stats);
      },
      (itemId) => {
        if (this.player.eat(itemId)) {
          this.hud.showToast(this.player.isPoisoned ? 'Coś tu było zepsute...' : 'Najedzony');
        }
        this.inventoryPanel.render(this.player.stats);
      },
    );
  }

  start(): void {
    this.renderer.setAnimationLoop(this.tick);
  }

  private hudDerived() {
    return {
      carriedWeight: this.player.carriedWeight,
      maxResource: this.player.effectiveMaxResource,
      skillName: SKILL_NAMES[this.player.primarySkillId],
      skillLevel: this.player.primarySkillLevel,
    };
  }

  /** Dev-only hooks (see main.ts) for driving the game from automated smoke tests. */
  debugTeleportPlayerTo(x: number, z: number): void {
    this.player.position.set(x, 0, z);
  }

  debugGiveItem(itemId: string, qty: number): boolean {
    return this.player.addItem(itemId, qty);
  }

  debugSetLevel(level: number): void {
    this.player.stats.level = level;
    applyLevelStats(this.player.stats);
  }

  debugTrainSkill(times: number): { leveledUp: boolean; newLevel: number } {
    let result = { leveledUp: false, newLevel: this.player.primarySkillLevel };
    for (let i = 0; i < times; i++) result = this.player.trainPrimarySkill();
    return result;
  }

  debugSetSkillLevel(skillId: SkillId, level: number): void {
    this.player.stats.skills[skillId] = { level, progress: 0 };
  }

  debugTakeDamage(amount: number) {
    return this.player.takeDamage(amount);
  }

  debugCastAbility(abilityId: string): void {
    this.castAbility(abilityId);
  }

  debugSetResource(amount: number): void {
    this.player.stats.resource = amount;
  }

  get debugMonsters() {
    return this.monsters;
  }

  get debugPlayerStats() {
    return this.player.stats;
  }

  get debugEffectiveAttack(): number {
    return this.player.effectiveAttack;
  }

  get debugTargetMonster() {
    return this.targetMonster;
  }

  private tick = (): void => {
    const dt = Math.min(this.clock.getDelta(), 0.1);

    if (!this.player.isDead) {
      this.player.update(dt, this.input.moveX, this.input.moveY);
      this.player.updateSurvival(dt);
      this.player.updateAbilities(dt);
      clampToWorld(this.player.position);
      this.updateCorpses(dt);
      this.updateTargets();
      this.handleMonsterUpdates(dt);
      this.handleActionInput();
      this.handleAbilityInput();
      this.updateAbilityUI();
    }

    this.updateCamera(dt);
    this.hud.update(this.player.stats, this.hudDerived());
    this.renderer.render(this.scene, this.camera);
  };

  private updateCorpses(dt: number): void {
    for (let i = this.corpses.length - 1; i >= 0; i--) {
      const corpse = this.corpses[i];
      corpse.update(dt);
      if (corpse.expired) {
        this.scene.remove(corpse.mesh);
        this.corpses.splice(i, 1);
        if (corpse === this.openedCorpse) {
          this.lootPanel.hide();
          this.openedCorpse = null;
        }
      }
    }

    if (this.openedCorpse && !this.player.isInRange(this.openedCorpse.mesh.position)) {
      this.lootPanel.hide();
      this.openedCorpse = null;
    }
  }

  /** Picks the single nearest interactable — a live monster or an unlooted corpse — and
   * flips the action button between "ATAK" and "SZUKAJ" to match (GDD Section 12). */
  private updateTargets(): void {
    let nearestMonster: Monster | null = null;
    let nearestMonsterDist = Infinity;
    for (const m of this.monsters) {
      if (!m.alive) continue;
      const d = this.player.position.distanceTo(m.mesh.position);
      if (d < nearestMonsterDist) {
        nearestMonsterDist = d;
        nearestMonster = m;
      }
    }

    let nearestCorpse: Corpse | null = null;
    let nearestCorpseDist = Infinity;
    for (const c of this.corpses) {
      if (!c.hasLoot) continue;
      const d = this.player.position.distanceTo(c.mesh.position);
      if (d < nearestCorpseDist) {
        nearestCorpseDist = d;
        nearestCorpse = c;
      }
    }

    if (nearestCorpse && nearestCorpseDist <= TARGET_SELECT_RADIUS && nearestCorpseDist <= nearestMonsterDist) {
      this.targetMonster = null;
      this.targetCorpse = nearestCorpse;
      this.input.setActionLabel('SZUKAJ');
    } else if (nearestMonster && nearestMonsterDist <= TARGET_SELECT_RADIUS) {
      this.targetMonster = nearestMonster;
      this.targetCorpse = null;
      this.input.setActionLabel('ATAK');
    } else {
      this.targetMonster = null;
      this.targetCorpse = null;
      this.input.setActionLabel('ATAK');
    }

    for (const m of this.monsters) {
      const mat = m.mesh.material as THREE.MeshStandardMaterial;
      mat.opacity = m === this.targetMonster ? 1 : 0.85;
      mat.emissive = m === this.targetMonster ? new THREE.Color(0x224422) : new THREE.Color(0x000000);
    }
  }

  private handleMonsterUpdates(dt: number): void {
    for (const monster of this.monsters) {
      const damage = monster.update(dt, this.player.position);
      if (damage > 0) {
        const result = this.player.takeDamage(damage);
        if (result.wardcraftLeveledUp) {
          this.hud.showToast(`${SKILL_NAMES.wardcraft} → ${result.wardcraftLevel}!`);
        }
        if (this.player.isDead) this.onPlayerDeath();
      }
    }
  }

  private handleActionInput(): void {
    if (!this.input.consumeAttack()) return;

    if (this.targetCorpse) {
      if (!this.player.isInRange(this.targetCorpse.mesh.position)) return;
      this.openCorpse(this.targetCorpse);
      return;
    }

    if (!this.player.tryAttack()) return;
    if (!this.targetMonster || !this.player.isInRange(this.targetMonster.mesh.position)) return;

    const wasAlive = this.targetMonster.alive;
    this.applyDamageToMonster(this.targetMonster, this.player.effectiveAttack);
    if (wasAlive) {
      const skillResult = this.player.trainPrimarySkill();
      if (skillResult.leveledUp) {
        this.hud.showToast(`${SKILL_NAMES[this.player.primarySkillId]} → ${skillResult.newLevel}!`);
      }
    }
  }

  /** Handles the 5 ability buttons + the A/B loadout switch (GDD Section 8/10). */
  private handleAbilityInput(): void {
    if (this.input.consumeLoadoutSwitch()) {
      this.currentLoadout = this.currentLoadout === 'A' ? 'B' : 'A';
      this.hud.showToast(`Zestaw ${this.currentLoadout}`);
    }

    if (this.currentLoadout !== 'A') return; // Loadout B has no abilities yet

    const loadout = CLASS_LOADOUT_A[this.player.stats.classId];
    for (let slot = 0; slot < loadout.length; slot++) {
      if (this.input.consumeAbility(slot)) this.castAbility(loadout[slot]);
    }
  }

  private castAbility(abilityId: string): void {
    const def = ABILITIES[abilityId];
    const { effect } = def;
    const needsTarget = effect.damageMultiplier !== undefined || effect.stunDuration !== undefined || effect.slowPercent !== undefined;

    if (needsTarget) {
      const inRange = this.targetMonster && this.player.position.distanceTo(this.targetMonster.mesh.position) <= def.range;
      if (!inRange) {
        this.hud.showToast('Brak celu w zasięgu');
        return;
      }
    }

    const result = this.player.tryUseAbility(abilityId);
    if (!result.ok) {
      this.hud.showToast(result.reason === 'cooldown' ? 'Jeszcze się ładuje' : 'Za mało zasobu');
      return;
    }

    if (needsTarget) {
      const target = this.targetMonster!;
      if (effect.damageMultiplier) {
        if (effect.aoeRadius) {
          const center = target.mesh.position;
          for (const m of this.monsters) {
            if (m.alive && m.mesh.position.distanceTo(center) <= effect.aoeRadius) {
              this.applyDamageToMonster(m, result.power);
            }
          }
        } else {
          this.applyDamageToMonster(target, result.power);
        }
      }
      if (target.alive) {
        if (effect.stunDuration) target.applyStun(effect.stunDuration);
        if (effect.slowPercent && effect.slowDuration) target.applySlow(effect.slowPercent, effect.slowDuration);
      }

      const skillResult = this.player.trainPrimarySkill();
      if (skillResult.leveledUp) {
        this.hud.showToast(`${SKILL_NAMES[this.player.primarySkillId]} → ${skillResult.newLevel}!`);
      }
    }

    this.hud.showToast(`${def.icon} ${def.name}`);
  }

  /** Shared by the basic attack and every damage-dealing ability — handles death, corpse, EXP. */
  private applyDamageToMonster(monster: Monster, amount: number): void {
    monster.takeDamage(amount);
    if (monster.alive) return;

    // GDD Section 12: EXP is awarded on the kill itself; gold/items go into
    // a corpse anyone can race to open, not straight to the killer.
    const { exp, gold, items } = monster.rollResult();
    const corpse = new Corpse(monster.def.name, monster.mesh.position, monster.def.color, { gold, items });
    this.corpses.push(corpse);
    this.scene.add(corpse.mesh);

    const leveledUp = this.player.gainExp(exp);
    this.hud.showToast(`+${exp} EXP — zwłoki ${monster.def.name} czekają na złupienie`);
    if (leveledUp) {
      this.hud.showToast(`Awans! Poziom ${this.player.stats.level}`);
      this.hud.flashLevelUp();
    }
    if (monster === this.targetMonster) this.targetMonster = null;
  }

  private updateAbilityUI(): void {
    const loadout = this.currentLoadout === 'A' ? CLASS_LOADOUT_A[this.player.stats.classId] : [];
    this.input.setLoadoutLabel(this.currentLoadout);
    for (let slot = 0; slot < 5; slot++) {
      const abilityId = loadout[slot];
      if (!abilityId) {
        this.input.setAbilityDisplay(slot, '', '', true);
        continue;
      }
      const def = ABILITIES[abilityId];
      const cd = this.player.getCooldownRemaining(abilityId);
      const affordable = this.player.stats.resource >= def.resourceCost;
      this.input.setAbilityDisplay(slot, def.icon, cd > 0 ? Math.ceil(cd).toString() : '', cd > 0 || !affordable);
    }
  }

  /** Opening reveals the contents (gold is auto-collected; items need an individual tap each). */
  private openCorpse(corpse: Corpse): void {
    const gold = corpse.collectGold();
    if (gold > 0) {
      this.player.gainGold(gold);
      this.hud.showToast(`+${gold} złota`);
    }
    this.openedCorpse = corpse;
    this.lootPanel.show(corpse.monsterName, corpse.loot.items, (itemId) => this.tryTakeItem(corpse, itemId));
  }

  private tryTakeItem(corpse: Corpse, itemId: string): void {
    const drop = corpse.peekItem(itemId);
    if (!drop) return; // someone else already took it

    if (!this.player.canCarry(drop.itemId, drop.qty)) {
      this.hud.showToast('Za ciężkie — plecak pełny');
      return;
    }

    corpse.takeItem(itemId);
    this.player.addItem(drop.itemId, drop.qty);
    this.lootPanel.render(corpse.loot.items);

    if (!corpse.hasLoot) {
      this.lootPanel.hide();
      this.openedCorpse = null;
    }
  }

  private onPlayerDeath(): void {
    this.hud.showToast('Zginąłeś... odradzanie');
    window.setTimeout(() => this.player.respawn(), 1500);
  }

  private updateCamera(dt: number): void {
    const desired = this.player.position.clone().add(CAMERA_OFFSET);
    this.camera.position.lerp(desired, 1 - Math.pow(0.001, dt));
    const lookAt = this.player.position.clone().add(new THREE.Vector3(0, 1, 0));
    this.camera.lookAt(lookAt);
  }

  private setupLighting(): void {
    const hemi = new THREE.HemisphereLight(0xffffff, 0x3a5f3a, 0.9);
    this.scene.add(hemi);

    const sun = new THREE.DirectionalLight(0xfff2d9, 1.1);
    sun.position.set(15, 25, -10);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    sun.shadow.camera.left = -30;
    sun.shadow.camera.right = 30;
    sun.shadow.camera.top = 30;
    sun.shadow.camera.bottom = -30;
    this.scene.add(sun);
  }

  private onResize = (): void => {
    this.camera.aspect = window.innerWidth / window.innerHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(window.innerWidth, window.innerHeight);
  };
}
