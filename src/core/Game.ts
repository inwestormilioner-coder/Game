import * as THREE from 'three';
import { Player } from '../entities/Player';
import { Monster } from '../entities/Monster';
import { Corpse } from '../entities/Corpse';
import { Npc } from '../entities/Npc';
import { GatherNode } from '../entities/GatherNode';
import { InputController } from '../input/InputController';
import { HUD } from '../ui/HUD';
import { LootPanel } from '../ui/LootPanel';
import { InventoryPanel } from '../ui/InventoryPanel';
import { DialoguePanel } from '../ui/DialoguePanel';
import { DepotPanel } from '../ui/DepotPanel';
import { MiniMap } from '../ui/MiniMap';
import { MonsterLabels } from '../ui/MonsterLabels';
import { PlayerLabel } from '../ui/PlayerLabel';
import { MapEditor } from '../editor/MapEditor';
import { buildWorld, clampToWorld, type Obstacle } from '../world/World';
import { MONSTER_DEFS } from '../data/monsters';
import { ABILITIES, CLASS_LOADOUT_A } from '../data/abilities';
import { NPCS } from '../data/npcs';
import { QUESTS } from '../data/quests';
import { GATHER_NODES } from '../data/gathering';
import { ITEMS } from '../data/items';
import { applyLevelStats, SKILL_NAMES, type ClassId, type GatherKind, type SkillId } from '../types';
import { ATTACK_RANGE, type GatherFailReason } from '../entities/Player';

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

// Fixed for every player — no rotation, no zoom (GDD Section 28). A wide-angle isometric-style
// view (reference: a mobile isometric ARPG town square) rather than the earlier close
// third-person chase camera — still one fixed offset for everyone, tuned down from an initial,
// too-steep-per-feedback pass toward a more comfortable ~50° downward angle.
const CAMERA_OFFSET = new THREE.Vector3(0, 11, -9);
const CAMERA_FOV = 45;

const TARGET_SELECT_RADIUS = 4;
// The 5 original abilities per class (green in the layout sketch) plus up to 2 sprint slots
// (yellow) — Mage uses both, everyone else uses 1 and leaves the 7th hidden (GDD Section 28).
const MAX_ABILITY_SLOTS = 7;
// Half-width of the aimed-attack joystick's cone (GDD Section 28) — a monster has to fall
// within this angle of the drag direction (and inside ATTACK_RANGE) to be attackable by it.
const AIM_CONE_HALF_ANGLE = (40 * Math.PI) / 180;
// Player capsule radius (matches Player.ts's CapsuleGeometry) — used for obstacle/monster collision.
const PLAYER_RADIUS = 0.4;
// NPCs are stationary and have no def.radius field of their own (unlike monsters) — a flat
// collision radius is enough since they never move.
const NPC_RADIUS = 0.4;

const GATHER_ACTION_LABEL: Record<GatherKind, string> = {
  mining: 'Kop',
  woodcutting: 'Rąb',
  fishing: 'Łów',
};

// Accusative form, for "Załóż ___" (equip ___) — gathering tools are equipped into
// the weapon slot, same as a combat weapon, not carried loose in the backpack.
const GATHER_TOOL_NAME: Record<GatherKind, string> = {
  mining: 'kilof',
  woodcutting: 'siekierę',
  fishing: 'wędkę',
};

export class Game {
  private readonly scene = new THREE.Scene();
  private readonly camera: THREE.PerspectiveCamera;
  private readonly renderer: THREE.WebGLRenderer;

  private readonly player: Player;
  private readonly monsters: Monster[] = [];
  private readonly corpses: Corpse[] = [];
  private readonly npcs: Npc[] = [];
  private readonly gatherNodes: GatherNode[] = [];
  private readonly obstacles: Obstacle[];
  private readonly input: InputController;
  private readonly hud: HUD;
  private readonly lootPanel: LootPanel;
  private readonly inventoryPanel: InventoryPanel;
  private readonly dialoguePanel: DialoguePanel;
  private readonly depotPanel: DepotPanel;
  private readonly miniMap: MiniMap;
  private readonly monsterLabels: MonsterLabels;
  private readonly playerLabel: PlayerLabel;
  private readonly aimReticle: THREE.Group;
  /** Dev-only ('M' key) — never constructed outside import.meta.env.DEV. */
  private readonly mapEditor: MapEditor | null;

  private clock = new THREE.Clock();
  private targetMonster: Monster | null = null;
  private targetCorpse: Corpse | null = null;
  private targetNpc: Npc | null = null;
  private targetNode: GatherNode | null = null;
  /** Live while the aim joystick is held (GDD Section 28) — the monster the cone is
   * currently pointed at, recomputed every frame; null when not aiming or nothing's in the cone. */
  private aimedMonster: Monster | null = null;
  /** The corpse the loot panel is currently showing, if any (distinct from targetCorpse,
   * which recomputes every frame by proximity and would otherwise yank the panel around). */
  private openedCorpse: Corpse | null = null;
  /** The NPC whose dialogue/depot screen is currently open, if any (same reasoning as openedCorpse). */
  private openedNpc: Npc | null = null;
  /** Loadout B is a switchable but currently empty placeholder (GDD Section 10). */
  private currentLoadout: 'A' | 'B' = 'A';

  constructor(root: HTMLElement, canvasHost: HTMLElement, classId: ClassId) {
    this.player = new Player(classId);
    this.scene.background = new THREE.Color(0x8fd0ff);
    this.scene.fog = new THREE.Fog(0x8fd0ff, 30, 75);

    this.camera = new THREE.PerspectiveCamera(
      CAMERA_FOV,
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
    this.obstacles = buildWorld(this.scene);
    this.scene.add(this.player.mesh);

    for (const [type, x, z] of MONSTER_SPAWNS) {
      const monster = new Monster(MONSTER_DEFS[type], new THREE.Vector3(x, 0, z));
      this.monsters.push(monster);
      this.scene.add(monster.mesh);
    }

    for (const def of Object.values(NPCS)) {
      const npc = new Npc(def);
      this.npcs.push(npc);
      this.scene.add(npc.mesh);
    }

    for (const def of Object.values(GATHER_NODES)) {
      const node = new GatherNode(def);
      this.gatherNodes.push(node);
      this.scene.add(node.mesh);
    }

    this.input = new InputController(root);
    this.hud = new HUD(root);
    this.lootPanel = new LootPanel(root);
    this.inventoryPanel = new InventoryPanel(root);
    this.dialoguePanel = new DialoguePanel(root);
    this.depotPanel = new DepotPanel(root);
    this.miniMap = new MiniMap(root);
    this.monsterLabels = new MonsterLabels(root, this.monsters);
    this.playerLabel = new PlayerLabel(root);
    this.aimReticle = this.buildAimReticle();
    this.scene.add(this.aimReticle);
    this.mapEditor = import.meta.env.DEV
      ? new MapEditor(this.scene, this.camera, this.renderer.domElement, this.obstacles, () => this.player.position)
      : null;
    this.hud.update(this.player.stats, this.hudDerived());

    root.querySelector('#capacity-btn')!.addEventListener('click', () => this.toggleInventory());
    this.renderer.domElement.addEventListener('pointerdown', this.onCanvasTap);

    window.addEventListener('resize', this.onResize);
  }

  /** Corpses (only corpses) are opened by tapping directly on them in the 3D world, not through
   * the unified action button — a deliberate exception, since "which body do I mean" is often
   * ambiguous from proximity alone when several are lying around, but never ambiguous under a
   * fingertip. Everything else (monsters/nodes/NPCs) stays on the single action button. */
  private onCanvasTap = (e: PointerEvent): void => {
    if (this.mapEditor?.active) return;
    if (this.isAnyPanelOpen()) return;

    const rect = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1,
    );
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(ndc, this.camera);
    const corpseMeshes = this.corpses.map((c) => c.mesh);
    const hit = raycaster.intersectObjects(corpseMeshes, false)[0];
    if (!hit) return;

    const corpse = this.corpses.find((c) => c.mesh === hit.object);
    if (!corpse) return;
    if (!this.player.isInRange(corpse.mesh.position)) {
      this.hud.showToast('Podejdź bliżej');
      return;
    }
    this.openCorpse(corpse);
  };

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

  get debugCorpses() {
    return this.corpses;
  }

  get debugDiscoveredCount(): number {
    return this.miniMap.discoveredCount;
  }

  get debugMiniMapViewRadius(): number {
    return this.miniMap.currentViewRadius;
  }

  get debugPlayerStats() {
    return this.player.stats;
  }

  get debugPlayerPosition() {
    return this.player.position;
  }

  get debugEffectiveAttack(): number {
    return this.player.effectiveAttack;
  }

  get debugPlayerSpeed(): number {
    return this.player.moveSpeed;
  }

  get debugPlayerIsStealthed(): boolean {
    return this.player.isStealthed;
  }

  get debugPlayerReflectPercent(): number {
    return this.player.reflectPercent;
  }

  /** Test-only: fires a real basic attack and reports the resulting cooldown, so a test can
   * verify Archer's sprint haste (buffAttackSpeedPercent) actually shortens ATTACK_COOLDOWN. */
  debugPlayerTryAttackCooldown(): number {
    this.player.tryAttack();
    return this.player.attackCooldownRemaining;
  }

  get debugTargetMonster() {
    return this.targetMonster;
  }

  get debugAimedMonster() {
    return this.aimedMonster;
  }

  get debugAimReticleVisible(): boolean {
    return this.aimReticle.visible;
  }

  get debugTargetNpc() {
    return this.targetNpc;
  }

  get debugNpcs() {
    return this.npcs;
  }

  get debugDialogueOpen(): boolean {
    return this.dialoguePanel.isOpen;
  }

  get debugDepotOpen(): boolean {
    return this.depotPanel.isOpen;
  }

  debugInteract(): void {
    if (this.targetNpc) this.interactWithNpc(this.targetNpc);
  }

  debugQuestState(questId: string) {
    return this.player.questState(questId);
  }

  /** Instantly kills up to `count` living monsters of the given def id (test-only shortcut
   * for quest-progress scenarios that would otherwise need real combat). */
  debugKillMonstersOfType(monsterId: string, count: number): void {
    let killed = 0;
    for (const monster of this.monsters) {
      if (killed >= count) break;
      if (!monster.alive || monster.def.id !== monsterId) continue;
      this.applyDamageToMonster(monster, monster.def.hp);
      killed++;
    }
  }

  get debugGatherNodes() {
    return this.gatherNodes;
  }

  get debugObstacles() {
    return this.obstacles;
  }

  get debugTargetNode() {
    return this.targetNode;
  }

  get debugCameraBasis() {
    const forward = new THREE.Vector3();
    this.camera.getWorldDirection(forward);
    const right = new THREE.Vector3();
    const up = new THREE.Vector3();
    this.camera.matrixWorld.extractBasis(right, up, new THREE.Vector3());
    return { forward: { x: forward.x, y: forward.y, z: forward.z }, right: { x: right.x, y: right.y, z: right.z } };
  }

  /** Projects a world XZ position to screen pixel coordinates — test-only helper so a
   * Playwright script can compute exactly where to click something in the 3D scene. */
  debugWorldToScreen(x: number, z: number, y = 0): { x: number; y: number } {
    const ndc = new THREE.Vector3(x, y, z).project(this.camera);
    return {
      x: (ndc.x * 0.5 + 0.5) * window.innerWidth,
      y: (1 - (ndc.y * 0.5 + 0.5)) * window.innerHeight,
    };
  }

  debugGather() {
    return this.targetNode ? this.tryGatherAt(this.targetNode) : undefined;
  }

  /** Gathers a specific node by id regardless of current proximity/targeting — a direct,
   * frame-timing-independent shortcut for tests (debugGather depends on the per-frame
   * targeting system having already run, which real gameplay doesn't need to race). */
  debugGatherAt(nodeId: string) {
    const node = this.gatherNodes.find((n) => n.def.id === nodeId);
    return node ? this.tryGatherAt(node) : undefined;
  }

  private tick = (): void => {
    const dt = Math.min(this.clock.getDelta(), 0.1);

    if (this.mapEditor?.active) {
      this.mapEditor.update(dt);
      this.updateCamera(dt);
      this.renderer.render(this.scene, this.camera);
      return;
    }

    if (!this.player.isDead) {
      this.player.update(dt, this.input.moveX, this.input.moveY);
      this.resolveCollisions();
      clampToWorld(this.player.position);
      this.player.updateSurvival(dt);
      this.player.updateAbilities(dt);
      this.updateCorpses(dt);
      this.updateGatherNodes(dt);
      this.updateTargets();
      this.updateAimReticle();
      this.handleMonsterUpdates(dt);
      this.handleActionInput();
      this.handleAbilityInput();
      this.updateAbilityUI();
      this.miniMap.reveal(this.player.position);
    }

    this.updateCamera(dt);
    this.hud.update(this.player.stats, this.hudDerived());
    this.miniMap.draw(this.player.position, this.player.facing, this.monsters);
    this.monsterLabels.update(this.camera, this.aimedMonster ?? this.targetMonster, window.innerWidth, window.innerHeight);
    this.playerLabel.update(this.camera, this.player.position, this.player.stats, window.innerWidth, window.innerHeight);
    this.renderer.render(this.scene, this.camera);
  };

  /** Pushes the player back out of anything solid — trees/rocks (static Obstacles) and living
   * monsters — instead of letting them walk straight through. Corpses and gathering nodes stay
   * walkable on purpose (a defeated monster's body isn't a wall, and stepping onto a vein/tree
   * is exactly how you'd target it under the unified action-button system). */
  private resolveCollisions(): void {
    const pos = this.player.position;

    for (const obstacle of this.obstacles) {
      this.pushOutOfCircle(pos, obstacle.x, obstacle.z, obstacle.radius);
    }

    for (const monster of this.monsters) {
      if (!monster.alive) continue;
      this.pushOutOfCircle(pos, monster.mesh.position.x, monster.mesh.position.z, monster.def.radius);
    }

    for (const npc of this.npcs) {
      this.pushOutOfCircle(pos, npc.mesh.position.x, npc.mesh.position.z, NPC_RADIUS);
    }
  }

  private pushOutOfCircle(pos: THREE.Vector3, cx: number, cz: number, radius: number): void {
    const minDist = radius + PLAYER_RADIUS;
    const dx = pos.x - cx;
    const dz = pos.z - cz;
    const dist = Math.hypot(dx, dz);
    if (dist >= minDist) return;
    if (dist < 1e-4) {
      pos.x = cx + minDist;
      return;
    }
    const push = minDist - dist;
    pos.x += (dx / dist) * push;
    pos.z += (dz / dist) * push;
  }

  /** The ground reticle shown while the attack joystick is held: a translucent wedge (the aim
   * cone) plus a thin full-circle rim (ATTACK_RANGE) — both flattened onto the XZ ground plane.
   * Built once and just repositioned/rotated/toggled each frame in updateAimReticle(). */
  private buildAimReticle(): THREE.Group {
    const group = new THREE.Group();
    group.visible = false;

    // Centered on local +Z (theta = -90°) so that, just like a character's rotation.y =
    // atan2(dx, dz), setting this group's rotation.y to that same angle points the wedge
    // at world direction (dx, dz) — see updateAimReticle.
    const wedgeGeo = new THREE.RingGeometry(
      0,
      ATTACK_RANGE,
      32,
      1,
      -Math.PI / 2 - AIM_CONE_HALF_ANGLE,
      AIM_CONE_HALF_ANGLE * 2,
    );
    wedgeGeo.rotateX(-Math.PI / 2);
    const wedge = new THREE.Mesh(
      wedgeGeo,
      new THREE.MeshBasicMaterial({ color: 0x4dd2ff, transparent: true, opacity: 0.25, side: THREE.DoubleSide, depthWrite: false }),
    );

    const rimGeo = new THREE.RingGeometry(ATTACK_RANGE - 0.04, ATTACK_RANGE, 48);
    rimGeo.rotateX(-Math.PI / 2);
    const rim = new THREE.Mesh(
      rimGeo,
      new THREE.MeshBasicMaterial({ color: 0x9fe8ff, transparent: true, opacity: 0.65, side: THREE.DoubleSide, depthWrite: false }),
    );

    group.add(wedge, rim);
    return group;
  }

  /** Runs every frame: shows/hides and orients the aim reticle, and recomputes which monster
   * (if any) the cone currently points at — handleActionInput() reads aimedMonster on an
   * 'aimed' release, and MonsterLabels highlights it in place of the auto-picked targetMonster
   * while aiming, so the player always sees exactly who they're about to hit. */
  private updateAimReticle(): void {
    if (!this.input.aiming) {
      // Deliberately NOT clearing aimedMonster here: aiming flips false the instant the
      // pointer lifts, in the same frame handleActionInput() still needs to read it for
      // the 'aimed' release it's about to consume. handleActionInput() clears it once done.
      this.aimReticle.visible = false;
      return;
    }

    // Same screen-to-world negation as the movement joystick (Game.ts's fixed camera has its
    // on-screen "right" pointing at world -X and "up" pointing at world +Z — Player.ts.update).
    let dx = -this.input.aimX;
    let dz = -this.input.aimY;
    const len = Math.hypot(dx, dz);
    if (len < 0.001) {
      dx = this.player.facing.x;
      dz = this.player.facing.z;
    } else {
      dx /= len;
      dz /= len;
    }
    const aimAngle = Math.atan2(dx, dz);

    this.aimReticle.visible = true;
    this.aimReticle.position.set(this.player.position.x, 0.03, this.player.position.z);
    this.aimReticle.rotation.y = aimAngle;

    let best: Monster | null = null;
    let bestDist = Infinity;
    for (const m of this.monsters) {
      if (!m.alive) continue;
      const mdx = m.mesh.position.x - this.player.position.x;
      const mdz = m.mesh.position.z - this.player.position.z;
      const dist = Math.hypot(mdx, mdz);
      if (dist > ATTACK_RANGE || dist < 1e-4) continue;
      const angleTo = Math.atan2(mdx, mdz);
      let diff = angleTo - aimAngle;
      diff = Math.atan2(Math.sin(diff), Math.cos(diff)); // wrap to [-pi, pi]
      if (Math.abs(diff) > AIM_CONE_HALF_ANGLE) continue;
      if (dist < bestDist) {
        bestDist = dist;
        best = m;
      }
    }
    this.aimedMonster = best;
  }

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

  private updateGatherNodes(dt: number): void {
    for (const node of this.gatherNodes) node.update(dt);
  }

  /** Monsters, lootable corpses, gathering nodes, and NPCs all compete for the single ATAK
   * button — whichever is nearest within range wins (ties broken corpse > monster > node > NPC,
   * the order they're pushed below). One button for everything, on purpose: no separate
   * gathering prompt (equip the matching tool and tap the target) and no separate "talk" button
   * either (target the NPC the same way and tap ATAK — simplicity over adding more buttons). */
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

    let nearestNode: GatherNode | null = null;
    let nearestNodeDist = Infinity;
    for (const node of this.gatherNodes) {
      if (node.depleted) continue;
      const d = this.player.position.distanceTo(node.mesh.position);
      if (d < nearestNodeDist) {
        nearestNodeDist = d;
        nearestNode = node;
      }
    }

    let nearestNpc: Npc | null = null;
    let nearestNpcDist = Infinity;
    for (const npc of this.npcs) {
      const d = npc.distanceTo(this.player.position);
      if (d < nearestNpcDist) {
        nearestNpcDist = d;
        nearestNpc = npc;
      }
    }

    type Candidate = { dist: number; apply: () => void };
    const candidates: Candidate[] = [];
    if (nearestCorpse && nearestCorpseDist <= TARGET_SELECT_RADIUS) {
      candidates.push({
        dist: nearestCorpseDist,
        apply: () => {
          this.targetCorpse = nearestCorpse;
          this.input.setActionLabel('SZUKAJ');
        },
      });
    }
    if (nearestMonster && nearestMonsterDist <= TARGET_SELECT_RADIUS) {
      candidates.push({
        dist: nearestMonsterDist,
        apply: () => {
          this.targetMonster = nearestMonster;
          this.input.setActionLabel('ATAK');
        },
      });
    }
    if (nearestNode && nearestNodeDist <= TARGET_SELECT_RADIUS) {
      candidates.push({
        dist: nearestNodeDist,
        apply: () => {
          this.targetNode = nearestNode;
          this.input.setActionLabel(GATHER_ACTION_LABEL[nearestNode!.def.kind]);
        },
      });
    }
    if (nearestNpc && nearestNpcDist <= TARGET_SELECT_RADIUS) {
      candidates.push({
        dist: nearestNpcDist,
        apply: () => {
          this.targetNpc = nearestNpc;
          this.input.setActionLabel(nearestNpc!.def.role === 'depot' ? 'Depozyt' : 'Rozmawiaj');
        },
      });
    }

    this.targetMonster = null;
    this.targetCorpse = null;
    this.targetNode = null;
    this.targetNpc = null;

    if (candidates.length > 0) {
      candidates.sort((a, b) => a.dist - b.dist);
      candidates[0].apply();
    } else {
      this.input.setActionLabel('ATAK');
    }

    // Per-mesh opacity/emissive tint used to live here, but it wasn't legible on a real
    // device — MonsterLabels' gold highlight (Section 10) is the actual "you're targeting
    // this" signal now, and it works the same whether a monster has a real model or not.

    if (this.openedNpc && this.openedNpc.distanceTo(this.player.position) > TARGET_SELECT_RADIUS) {
      this.dialoguePanel.hide();
      this.depotPanel.hide();
      this.openedNpc = null;
    }
  }

  private isAnyPanelOpen(): boolean {
    return this.dialoguePanel.isOpen || this.depotPanel.isOpen || this.inventoryPanel.isOpen || this.lootPanel.isOpen;
  }

  /** Mining/Woodcutting/Fishing (gathering professions) — deterministic yield, gated by skill
   * level (node access) and tool/bait tier (whether the attempt succeeds at all). */
  private tryGatherAt(node: GatherNode) {
    const result = this.player.tryGather(node.def);
    if (!result.ok) {
      const message = this.gatherFailMessage(node.def.kind, result.reason!);
      if (message) this.hud.showToast(message);
      return result;
    }

    node.deplete();
    const itemName = ITEMS[node.def.yieldItemId].name;
    this.hud.showToast(`+${result.qty} ${itemName}`);
    if (result.leveledUp) {
      this.hud.showToast(`${SKILL_NAMES[node.def.kind]} → ${result.newLevel}!`);
    }
    return result;
  }

  private gatherFailMessage(kind: GatherKind, reason: GatherFailReason): string | null {
    switch (reason) {
      case 'cooldown':
        return null; // silent, same as an attack still on cooldown
      case 'skillTooLow':
        return `Potrzebujesz wyższego poziomu ${SKILL_NAMES[kind]}`;
      case 'noTool':
        return `Załóż ${GATHER_TOOL_NAME[kind]}`;
      case 'toolTooWeak':
        return 'Twoje narzędzie jest za słabe';
      case 'noBait':
        return 'Potrzebujesz przynęty';
      case 'baitTooWeak':
        return 'Twoja przynęta jest za słaba';
      case 'full':
        return 'Za ciężkie — plecak pełny';
    }
  }

  private interactWithNpc(npc: Npc): void {
    this.openedNpc = npc;
    const { def } = npc;

    if (def.role === 'depot') {
      this.depotPanel.show(
        this.player.stats,
        (itemId) => {
          this.player.depositItem(itemId);
          this.depotPanel.render(this.player.stats);
        },
        (itemId) => {
          if (!this.player.withdrawItem(itemId)) this.hud.showToast('Za ciężkie — plecak pełny');
          this.depotPanel.render(this.player.stats);
        },
      );
      return;
    }

    if (def.role === 'ferryman') {
      const dest = def.destination!;
      const fare = def.fare ?? 0;
      this.dialoguePanel.show(def.name, `${def.idleText} The crossing to ${dest.name} costs ${fare} Glints.`, [
        {
          label: `Zapłać ${fare} i płyń`,
          onClick: () => {
            if (this.player.stats.gold < fare) {
              this.hud.showToast('Za mało złota');
              return;
            }
            this.player.stats.gold -= fare;
            this.player.position.set(dest.x, 0, dest.z);
            this.hud.showToast(`Przybijasz do brzegu: ${dest.name}`);
            this.dialoguePanel.hide();
            this.openedNpc = null;
          },
        },
        { label: 'Nie teraz', onClick: () => this.dialoguePanel.hide() },
      ]);
      return;
    }

    // role === 'quest'
    const quest = Object.values(QUESTS).find((q) => q.giverId === def.id);
    if (!quest) {
      this.dialoguePanel.show(def.name, def.idleText, [{ label: 'Zamknij', onClick: () => this.dialoguePanel.hide() }]);
      return;
    }

    const state = this.player.questState(quest.id);
    if (!state) {
      this.dialoguePanel.show(def.name, quest.offerText, [
        {
          label: 'Przyjmij zadanie',
          onClick: () => {
            this.player.startQuest(quest.id);
            this.hud.showToast(`Nowe zadanie: ${quest.name}`);
            this.dialoguePanel.hide();
          },
        },
        { label: 'Nie teraz', onClick: () => this.dialoguePanel.hide() },
      ]);
    } else if (state.status === 'active') {
      this.dialoguePanel.show(def.name, quest.activeText, [{ label: 'Zamknij', onClick: () => this.dialoguePanel.hide() }]);
    } else if (state.status === 'readyToTurnIn') {
      this.dialoguePanel.show(def.name, quest.turnInText, [
        {
          label: 'Oddaj zadanie',
          onClick: () => {
            const result = this.player.turnInQuest(quest.id);
            if (result.ok) {
              this.hud.showToast(`Zadanie ukończone: +${quest.rewardXp} EXP, +${quest.rewardGold} złota`);
              if (result.leveledUp) {
                this.hud.showToast(`Awans! Poziom ${this.player.stats.level}`);
                this.hud.flashLevelUp();
              }
            }
            this.dialoguePanel.hide();
          },
        },
      ]);
    } else {
      this.dialoguePanel.show(def.name, def.idleText, [{ label: 'Zamknij', onClick: () => this.dialoguePanel.hide() }]);
    }
  }

  private handleMonsterUpdates(dt: number): void {
    for (const monster of this.monsters) {
      const damage = monster.update(dt, this.player.position, this.player.isStealthed);
      if (damage > 0) {
        const result = this.player.takeDamage(damage);
        if (result.wardcraftLeveledUp) {
          this.hud.showToast(`${SKILL_NAMES.wardcraft} → ${result.wardcraftLevel}!`);
        }
        // Knight's sprint barrier (Section 28) — reflects a fraction of what actually got
        // through (post-block, post-armor) back at whichever monster just landed the hit.
        if (result.dealt > 0 && this.player.reflectPercent > 0) {
          monster.takeDamage(Math.round(result.dealt * this.player.reflectPercent));
        }
        if (this.player.isDead) this.onPlayerDeath();
      }
    }
  }

  private handleActionInput(): void {
    const release = this.input.consumeAttack();
    if (!release) return;
    if (this.isAnyPanelOpen()) return;

    // A real drag-and-release on the attack joystick (GDD Section 28) is unambiguously
    // "fight in this direction" — it bypasses corpse/node/NPC interaction entirely (aiming
    // at those doesn't make sense) and attacks whatever the cone landed on, if anything.
    if (release === 'aimed') {
      const monster = this.aimedMonster;
      this.aimedMonster = null; // consumed — see the comment in updateAimReticle()
      if (!monster) {
        this.hud.showToast('Brak celu w tym kierunku');
        return;
      }
      if (!this.player.tryAttack()) return;
      this.attackMonster(monster);
      return;
    }

    if (this.targetCorpse) {
      if (!this.player.isInRange(this.targetCorpse.mesh.position)) return;
      this.openCorpse(this.targetCorpse);
      return;
    }

    if (this.targetNode) {
      if (!this.player.isInRange(this.targetNode.mesh.position)) return;
      this.tryGatherAt(this.targetNode);
      return;
    }

    if (this.targetNpc) {
      if (!this.player.isInRange(this.targetNpc.mesh.position)) return;
      this.interactWithNpc(this.targetNpc);
      return;
    }

    if (!this.targetMonster) {
      this.hud.showToast('Brak celu w zasięgu');
      return;
    }

    if (!this.player.tryAttack()) return;
    if (!this.player.isInRange(this.targetMonster.mesh.position)) {
      this.hud.showToast('Podejdź bliżej');
      return;
    }

    this.attackMonster(this.targetMonster);
  }

  /** Shared by both the quick-tap (auto-picked target) and aimed (cone-picked target)
   * attack paths — everything after "we have a monster and tryAttack() already succeeded". */
  private attackMonster(monster: Monster): void {
    const wasAlive = monster.alive;
    this.applyDamageToMonster(monster, this.player.effectiveAttack);
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

    const readyQuests = this.player.registerMonsterKill(monster.def.id);
    for (const questId of readyQuests) {
      this.hud.showToast(`Zadanie gotowe do oddania: ${QUESTS[questId].name}`);
    }

    if (monster === this.targetMonster) this.targetMonster = null;
  }

  private updateAbilityUI(): void {
    const loadout = this.currentLoadout === 'A' ? CLASS_LOADOUT_A[this.player.stats.classId] : [];
    this.input.setLoadoutLabel(this.currentLoadout);
    for (let slot = 0; slot < MAX_ABILITY_SLOTS; slot++) {
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

  /** Opening just reveals the contents — gold sits in the list like any other pickup now,
   * nothing is collected automatically. */
  private openCorpse(corpse: Corpse): void {
    this.openedCorpse = corpse;
    this.lootPanel.show(
      corpse.monsterName,
      corpse.loot.items,
      corpse.loot.gold,
      (itemId) => this.tryTakeItem(corpse, itemId),
      () => this.tryTakeGold(corpse),
    );
  }

  private tryTakeGold(corpse: Corpse): void {
    const gold = corpse.collectGold();
    if (gold <= 0) return; // someone else already took it
    this.player.gainGold(gold);
    this.hud.showToast(`+${gold} złota`);
    this.lootPanel.render(corpse.loot.items, corpse.loot.gold);

    if (!corpse.hasLoot) {
      this.lootPanel.hide();
      this.openedCorpse = null;
    }
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
    this.lootPanel.render(corpse.loot.items, corpse.loot.gold);

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
    const editing = this.mapEditor?.active ?? false;
    const focus = editing ? this.mapEditor!.cameraFocus : this.player.position;
    const zoom = editing ? this.mapEditor!.cameraZoom : 1;
    const desired = focus.clone().add(CAMERA_OFFSET.clone().multiplyScalar(zoom));
    // Snap instantly while editing (no smoothing) — the map editor's ground raycast needs
    // the camera to be exactly where the pan/zoom inputs put it, every frame, so clicking
    // the same screen spot twice in a row reliably hits the same world point.
    if (editing) this.camera.position.copy(desired);
    else this.camera.position.lerp(desired, 1 - Math.pow(0.001, dt));
    const lookAt = focus.clone().add(new THREE.Vector3(0, 1, 0));
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
