import * as THREE from 'three';
import { Player } from '../entities/Player';
import { Monster } from '../entities/Monster';
import { InputController } from '../input/InputController';
import { HUD } from '../ui/HUD';
import { buildWorld, clampToWorld } from '../world/World';

const MONSTER_SPAWN_POINTS: Array<[number, number]> = [
  [6, 4], [-8, 5], [10, -6], [-5, -9], [14, 8], [-14, -3], [3, 14], [-3, -14],
];

// Fixed for every player — no rotation, no zoom (GDD Section 28). Seeing
// further is the minimap's job (Section 10), never the combat camera's.
const CAMERA_OFFSET = new THREE.Vector3(0, 6.5, -7);

export class Game {
  private readonly scene = new THREE.Scene();
  private readonly camera: THREE.PerspectiveCamera;
  private readonly renderer: THREE.WebGLRenderer;

  private readonly player = new Player();
  private readonly monsters: Monster[] = [];
  private readonly input: InputController;
  private readonly hud: HUD;

  private clock = new THREE.Clock();
  private targetMonster: Monster | null = null;

  constructor(root: HTMLElement, canvasHost: HTMLElement) {
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

    for (const [x, z] of MONSTER_SPAWN_POINTS) {
      const monster = new Monster(new THREE.Vector3(x, 0, z));
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

  private tick = (): void => {
    const dt = Math.min(this.clock.getDelta(), 0.1);

    if (!this.player.isDead) {
      this.player.update(dt, this.input.moveX, this.input.moveY);
      clampToWorld(this.player.position);
      this.updateTargetMonster();
      this.handleMonsterUpdates(dt);
      this.handleAttackInput();
    }

    this.updateCamera(dt);
    this.hud.update(this.player.stats);
    this.renderer.render(this.scene, this.camera);
  };

  private updateTargetMonster(): void {
    let nearest: Monster | null = null;
    let nearestDist = Infinity;
    for (const m of this.monsters) {
      if (!m.alive) continue;
      const d = this.player.position.distanceTo(m.mesh.position);
      if (d < nearestDist) {
        nearestDist = d;
        nearest = m;
      }
    }
    this.targetMonster = nearest && nearestDist <= 4 ? nearest : null;

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

  private handleAttackInput(): void {
    if (!this.input.consumeAttack()) return;
    if (!this.player.tryAttack()) return;
    if (!this.targetMonster || !this.player.isInRange(this.targetMonster.mesh.position)) return;

    this.targetMonster.takeDamage(this.player.stats.attack);
    if (!this.targetMonster.alive) {
      const { exp, gold } = this.targetMonster.drop;
      this.player.gainGold(gold);
      const leveledUp = this.player.gainExp(exp);
      this.hud.showToast(`+${exp} EXP  +${gold} złota`);
      if (leveledUp) {
        this.hud.showToast(`Awans! Poziom ${this.player.stats.level}`);
        this.hud.flashLevelUp();
      }
      this.targetMonster = null;
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
