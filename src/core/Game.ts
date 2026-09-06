import * as THREE from 'three';
import { Player } from '../entities/Player';
import { Monster } from '../entities/Monster';
import { Corpse } from '../entities/Corpse';
import { InputController } from '../input/InputController';
import { HUD } from '../ui/HUD';
import { buildWorld, clampToWorld } from '../world/World';
import { MONSTER_DEFS } from '../data/monsters';
import { ITEMS } from '../data/items';
import type { ClassId } from '../types';

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

  private clock = new THREE.Clock();
  private targetMonster: Monster | null = null;
  private targetCorpse: Corpse | null = null;

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
    this.hud.update(this.player.stats);

    window.addEventListener('resize', this.onResize);
  }

  start(): void {
    this.renderer.setAnimationLoop(this.tick);
  }

  /** Dev-only hook (see main.ts) for driving the game from automated smoke tests. */
  debugTeleportPlayerTo(x: number, z: number): void {
    this.player.position.set(x, 0, z);
  }

  get debugPlayerStats() {
    return this.player.stats;
  }

  get debugTargetMonster() {
    return this.targetMonster;
  }

  private tick = (): void => {
    const dt = Math.min(this.clock.getDelta(), 0.1);

    if (!this.player.isDead) {
      this.player.update(dt, this.input.moveX, this.input.moveY);
      clampToWorld(this.player.position);
      this.updateCorpses(dt);
      this.updateTargets();
      this.handleMonsterUpdates(dt);
      this.handleActionInput();
    }

    this.updateCamera(dt);
    this.hud.update(this.player.stats);
    this.renderer.render(this.scene, this.camera);
  };

  private updateCorpses(dt: number): void {
    for (let i = this.corpses.length - 1; i >= 0; i--) {
      const corpse = this.corpses[i];
      corpse.update(dt);
      if (corpse.expired) {
        this.scene.remove(corpse.mesh);
        this.corpses.splice(i, 1);
      }
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
      if (c.looted) continue;
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
        this.player.takeDamage(damage);
        if (this.player.isDead) this.onPlayerDeath();
      }
    }
  }

  private handleActionInput(): void {
    if (!this.input.consumeAttack()) return;

    if (this.targetCorpse) {
      if (!this.player.isInRange(this.targetCorpse.mesh.position)) return;
      this.lootCorpse(this.targetCorpse);
      this.targetCorpse = null;
      return;
    }

    if (!this.player.tryAttack()) return;
    if (!this.targetMonster || !this.player.isInRange(this.targetMonster.mesh.position)) return;

    this.targetMonster.takeDamage(this.player.stats.attack);
    if (!this.targetMonster.alive) {
      // GDD Section 12: EXP is awarded on the kill itself; gold/items go into
      // a corpse anyone can race to open, not straight to the killer.
      const { exp, gold, items } = this.targetMonster.rollResult();
      const corpse = new Corpse(this.targetMonster.mesh.position, this.targetMonster.def.color, { gold, items });
      this.corpses.push(corpse);
      this.scene.add(corpse.mesh);

      const leveledUp = this.player.gainExp(exp);
      this.hud.showToast(`+${exp} EXP — zwłoki ${this.targetMonster.def.name} czekają na złupienie`);
      if (leveledUp) {
        this.hud.showToast(`Awans! Poziom ${this.player.stats.level}`);
        this.hud.flashLevelUp();
      }
      this.targetMonster = null;
    }
  }

  private lootCorpse(corpse: Corpse): void {
    const { gold, items } = corpse.open();
    this.player.gainGold(gold);
    for (const drop of items) this.player.addItem(drop.itemId, drop.qty);

    const itemText = items
      .map((drop) => (drop.qty > 1 ? `${ITEMS[drop.itemId].name} x${drop.qty}` : ITEMS[drop.itemId].name))
      .join(', ');
    this.hud.showToast(`+${gold} złota${itemText ? '  ' + itemText : ''}`);
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
