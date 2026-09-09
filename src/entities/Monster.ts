import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { WORLD_RADIUS } from '../world/World';
import { rollLoot, type LootDrop } from '../systems/loot';
import type { MonsterDef } from '../data/monsters';

export interface MonsterResult {
  exp: number;
  items: LootDrop[];
}

// Death holds its last frame for a beat before the mesh actually disappears (respawnDelay,
// often several times longer, keeps counting down underneath — this is purely visual).
const DEATH_LINGER_SECONDS = 1.5;
const ATTACK_ANIM_SECONDS = 0.6;
const HIT_ANIM_SECONDS = 0.3;
const DEATH_ANIM_SECONDS = 1.2;
const LOOP_CROSSFADE_SECONDS = 0.15;

export class Monster {
  readonly mesh: THREE.Group;
  readonly def: MonsterDef;
  hp: number;
  alive = true;

  private respawnTimer = 0;
  private deathLingerTimer = 0;
  private wanderTarget = new THREE.Vector3();
  private wanderTimer = 0;
  private attackTimer = 0;
  private stunRemaining = 0;
  private slowPercent = 0;
  private slowRemaining = 0;
  private readonly homePosition: THREE.Vector3;

  private readonly placeholder: THREE.Mesh;
  private mixer: THREE.AnimationMixer | null = null;
  private clips: Record<string, THREE.AnimationClip> = {};
  private currentAction: THREE.AnimationAction | null = null;
  private currentLoopName: string | null = null;
  private attackAnimTimer = 0;
  private hitAnimTimer = 0;
  private deathAnimTriggered = false;

  constructor(def: MonsterDef, spawnPosition: THREE.Vector3) {
    this.def = def;
    this.hp = def.hp;
    this.homePosition = spawnPosition.clone();
    this.mesh = new THREE.Group();

    this.placeholder = new THREE.Mesh(
      new THREE.SphereGeometry(def.radius, 12, 12),
      new THREE.MeshStandardMaterial({ color: def.color, roughness: 0.5 }),
    );
    this.placeholder.castShadow = true;
    this.mesh.add(this.placeholder);

    this.mesh.position.copy(spawnPosition);
    this.mesh.position.y = def.radius;
    this.pickNewWanderTarget();

    if (def.modelPath) this.loadModel(def.modelPath, def.modelScale ?? 1);
  }

  private loadModel(path: string, scale: number): void {
    new GLTFLoader().load(
      path,
      (gltf) => {
        this.mesh.remove(this.placeholder);

        const model = gltf.scene;
        model.scale.setScalar(scale);
        model.traverse((obj) => {
          if ((obj as THREE.Mesh).isMesh) obj.castShadow = true;
        });
        this.mesh.add(model);

        this.mixer = new THREE.AnimationMixer(model);
        for (const clip of gltf.animations) this.clips[clip.name] = clip;
        this.setLoop('Idle');
      },
      undefined,
      (err) => {
        console.error(`Failed to load monster model "${path}" — keeping the placeholder mesh`, err);
      },
    );
  }

  private setLoop(name: string): void {
    if (!this.mixer || this.currentLoopName === name) return;
    const clip = this.clips[name];
    if (!clip) return;

    const action = this.mixer.clipAction(clip);
    action.reset();
    action.setLoop(THREE.LoopRepeat, Infinity);
    action.clampWhenFinished = false;
    action.enabled = true;
    action.fadeIn(LOOP_CROSSFADE_SECONDS).play();

    if (this.currentAction && this.currentAction !== action) this.currentAction.fadeOut(LOOP_CROSSFADE_SECONDS);
    this.currentAction = action;
    this.currentLoopName = name;
  }

  private playOneShot(name: string, targetSeconds: number): void {
    if (!this.mixer) return;
    const clip = this.clips[name];
    if (!clip) return;

    const action = this.mixer.clipAction(clip);
    action.reset();
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
    action.timeScale = clip.duration / targetSeconds;
    action.enabled = true;
    action.fadeIn(0.1).play();

    if (this.currentAction && this.currentAction !== action) this.currentAction.fadeOut(0.1);
    this.currentAction = action;
    this.currentLoopName = null;
  }

  private updateAnimation(dt: number, moving: boolean): void {
    if (!this.mixer) return;
    this.mixer.update(dt);

    if (!this.alive) {
      if (!this.deathAnimTriggered) {
        this.deathAnimTriggered = true;
        this.playOneShot('Death', DEATH_ANIM_SECONDS);
      }
      return;
    }
    this.deathAnimTriggered = false;

    if (this.attackAnimTimer > 0) {
      this.attackAnimTimer -= dt;
      return;
    }
    if (this.hitAnimTimer > 0) {
      this.hitAnimTimer -= dt;
      return;
    }

    this.setLoop(moving ? 'Walk' : 'Idle');
  }

  get maxHp(): number {
    return this.def.hp;
  }

  private pickNewWanderTarget(): void {
    const angle = Math.random() * Math.PI * 2;
    const dist = Math.random() * 3;
    this.wanderTarget
      .set(
        this.homePosition.x + Math.cos(angle) * dist,
        this.def.radius,
        this.homePosition.z + Math.sin(angle) * dist,
      )
      .clampLength(0, WORLD_RADIUS - 1);
    this.wanderTimer = 2 + Math.random() * 2;
  }

  /** Returns damage dealt to the player this frame, if any. `playerStealthed` (Assassin's
   * sprint ability — GDD Section 28) makes the player undetectable to aggro logic for every
   * monster except isBoss ones, checked fresh every frame — a monster already mid-chase drops
   * it (falls back to wandering) the instant stealth kicks in, not just for new aggro rolls. */
  update(dt: number, playerPosition: THREE.Vector3, playerStealthed = false): number {
    if (!this.alive) {
      this.updateAnimation(dt, false);
      if (this.deathLingerTimer > 0) {
        this.deathLingerTimer -= dt;
        if (this.deathLingerTimer <= 0) this.mesh.visible = false;
      }
      this.respawnTimer -= dt;
      if (this.respawnTimer <= 0) this.respawn();
      return 0;
    }

    if (this.attackTimer > 0) this.attackTimer -= dt;

    if (this.slowRemaining > 0) {
      this.slowRemaining -= dt;
      if (this.slowRemaining <= 0) this.slowPercent = 0;
    }

    if (this.stunRemaining > 0) {
      this.stunRemaining -= dt;
      this.updateAnimation(dt, false);
      return 0; // frozen — no movement, no attacks, while stunned
    }

    const moveSpeed = this.def.moveSpeed * (1 - this.slowPercent);
    const distToPlayer = this.mesh.position.distanceTo(playerPosition);
    const canDetectPlayer = !playerStealthed || this.def.isBoss === true;
    const inAggro = canDetectPlayer && distToPlayer <= this.def.aggroRange;

    if (this.def.behavior === 'passive') {
      if (inAggro) {
        this.fleeFrom(playerPosition, dt, moveSpeed);
        this.updateAnimation(dt, true);
        return 0;
      }
    } else if (inAggro) {
      if (distToPlayer > this.def.attackRange) {
        this.stepToward(playerPosition, moveSpeed, dt);
        this.updateAnimation(dt, true);
      } else if (this.attackTimer <= 0) {
        this.attackTimer = this.def.attackCooldown;
        this.attackAnimTimer = ATTACK_ANIM_SECONDS;
        this.playOneShot('Attack', ATTACK_ANIM_SECONDS);
        this.updateAnimation(dt, false);
        return this.def.damageMin + Math.floor(Math.random() * (this.def.damageMax - this.def.damageMin + 1));
      } else {
        this.updateAnimation(dt, false);
      }
      return 0;
    }

    this.wanderTimer -= dt;
    if (this.wanderTimer <= 0) this.pickNewWanderTarget();
    this.stepToward(this.wanderTarget, moveSpeed, dt);
    this.updateAnimation(dt, true);
    return 0;
  }

  /** Stacks/refreshes to the stronger of the current and incoming effect (GDD Section 8 abilities). */
  applyStun(duration: number): void {
    this.stunRemaining = Math.max(this.stunRemaining, duration);
  }

  applySlow(percent: number, duration: number): void {
    this.slowPercent = Math.max(this.slowPercent, percent);
    this.slowRemaining = Math.max(this.slowRemaining, duration);
  }

  private stepToward(target: THREE.Vector3, speed: number, dt: number): void {
    const dir = new THREE.Vector3().subVectors(target, this.mesh.position);
    dir.y = 0;
    if (dir.length() <= 0.1) return;
    dir.normalize();
    this.mesh.position.addScaledVector(dir, speed * dt);
    this.mesh.position.y = this.def.radius;
    this.mesh.rotation.y = Math.atan2(dir.x, dir.z);
  }

  private fleeFrom(threat: THREE.Vector3, dt: number, speed: number): void {
    const away = new THREE.Vector3().subVectors(this.mesh.position, threat);
    away.y = 0;
    if (away.lengthSq() <= 0.0001) return;
    away.normalize();
    this.mesh.position.addScaledVector(away, speed * 1.3 * dt);
    this.mesh.position.y = this.def.radius;
    this.mesh.rotation.y = Math.atan2(away.x, away.z);
  }

  takeDamage(amount: number): void {
    if (!this.alive) return;
    this.hp = Math.max(0, this.hp - amount);

    if (amount > 0 && this.hp > 0) {
      this.hitAnimTimer = HIT_ANIM_SECONDS;
      this.playOneShot('HitReaction', HIT_ANIM_SECONDS);
    }

    if (this.hp <= 0) this.die();
  }

  /** Call once, right after a kill — rolls gold/loot, so don't call it twice for one death.
   * Gold is just a Gold Coin item stack now (GDD's physical-coin currency), not a separate field. */
  rollResult(): MonsterResult {
    const gold = this.def.goldMin + Math.floor(Math.random() * (this.def.goldMax - this.def.goldMin + 1));
    const items = rollLoot(this.def.lootTable);
    if (gold > 0) items.unshift({ itemId: 'goldCoin', qty: gold });
    return { exp: this.def.xp, items };
  }

  private die(): void {
    this.alive = false;
    this.respawnTimer = this.def.respawnDelay;
    this.deathLingerTimer = this.mixer ? DEATH_LINGER_SECONDS : 0;
    this.stunRemaining = 0;
    this.slowPercent = 0;
    this.slowRemaining = 0;
    if (!this.mixer) this.mesh.visible = false; // no death clip to show — vanish immediately as before
  }

  private respawn(): void {
    this.alive = true;
    this.hp = this.def.hp;
    this.mesh.visible = true;
    this.mesh.position.copy(this.homePosition);
    this.mesh.position.y = this.def.radius;
    this.pickNewWanderTarget();
    this.deathAnimTriggered = false;
    this.attackAnimTimer = 0;
    this.hitAnimTimer = 0;
    this.currentLoopName = null;
    this.setLoop('Idle');
  }
}
