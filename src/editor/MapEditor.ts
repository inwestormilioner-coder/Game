import * as THREE from 'three';
import type { Obstacle } from '../world/World';

const GROUND_PLANE = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
const PICK_RADIUS = 0.7;
const PAN_SPEED = 14;
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 4;

/** Dev-only in-game map editor ('M' toggles it — never wired up outside import.meta.env.DEV).
 * Lets you click to place trees/rocks directly on the live 3D world (they're immediately
 * real Obstacles, collidable like any other), then export everything as a ready-to-paste
 * src/world/customLayout.ts array. Pre-existing (procedural or already-custom) obstacles are
 * shown for context and included in the export, but only entries placed THIS session can be
 * removed by clicking them again — editing the old ones is a hand-edit-the-export job. */
export class MapEditor {
  active = false;
  currentType: Obstacle['type'] = 'tree';
  readonly cameraFocus = new THREE.Vector3();
  cameraZoom = 1.6;

  private readonly raycaster = new THREE.Raycaster();
  private readonly preview: THREE.Group;
  private readonly placed: Array<{ obstacle: Obstacle; mesh: THREE.Object3D }> = [];
  private readonly panKeys = new Set<string>();
  private readonly treeMat = new THREE.MeshStandardMaterial({ color: 0x2d5a2d });
  private readonly trunkMat = new THREE.MeshStandardMaterial({ color: 0x5a3d20 });
  private readonly rockMat = new THREE.MeshStandardMaterial({ color: 0x777777, roughness: 0.9 });
  private readonly hint: HTMLDivElement;
  private readonly exportBox: HTMLTextAreaElement;
  private readonly scene: THREE.Scene;
  private readonly camera: THREE.PerspectiveCamera;
  private readonly domElement: HTMLElement;
  private readonly obstacles: Obstacle[];
  private readonly getPlayerPosition: () => THREE.Vector3;

  constructor(
    scene: THREE.Scene,
    camera: THREE.PerspectiveCamera,
    domElement: HTMLElement,
    obstacles: Obstacle[],
    getPlayerPosition: () => THREE.Vector3,
  ) {
    this.scene = scene;
    this.camera = camera;
    this.domElement = domElement;
    this.obstacles = obstacles;
    this.getPlayerPosition = getPlayerPosition;

    this.preview = this.buildGhost('tree');
    this.preview.visible = false;
    this.scene.add(this.preview);

    this.hint = document.createElement('div');
    this.hint.style.cssText =
      'position:fixed;left:10px;top:10px;z-index:9999;background:rgba(0,0,0,0.75);color:#fff;' +
      'font:12px/1.5 monospace;padding:8px 10px;border-radius:6px;white-space:pre;display:none;pointer-events:none;';
    document.body.appendChild(this.hint);

    this.exportBox = document.createElement('textarea');
    this.exportBox.style.cssText =
      'position:fixed;inset:5%;z-index:10000;font:12px/1.4 monospace;padding:10px;display:none;';
    this.exportBox.addEventListener('pointerdown', (e) => e.stopPropagation());
    this.exportBox.addEventListener('click', () => this.exportBox.select());
    document.body.appendChild(this.exportBox);

    window.addEventListener('keydown', this.onKeyDown);
    window.addEventListener('keyup', this.onKeyUp);
    domElement.addEventListener('pointerdown', this.onPointerDown);
    domElement.addEventListener('pointermove', this.onPointerMove);
    domElement.addEventListener('wheel', this.onWheel, { passive: false });
  }

  /** Called every frame from Game.ts (only while active — otherwise cheap to skip). */
  update(dt: number): void {
    if (!this.active) return;
    let x = 0;
    let z = 0;
    if (this.panKeys.has('a')) x -= 1;
    if (this.panKeys.has('d')) x += 1;
    if (this.panKeys.has('w')) z -= 1;
    if (this.panKeys.has('s')) z += 1;
    const len = Math.hypot(x, z);
    if (len > 0) {
      // Same screen-to-world negation as player movement, so WASD pans the view the same
      // visual direction it would move the character (Player.ts.update).
      this.cameraFocus.x += (-x / len) * PAN_SPEED * dt;
      this.cameraFocus.z += (-z / len) * PAN_SPEED * dt;
    }
  }

  private toggle(): void {
    this.active = !this.active;
    this.hint.style.display = this.active ? 'block' : 'none';
    this.preview.visible = false;
    if (this.active) {
      this.cameraFocus.copy(this.getPlayerPosition());
      this.panKeys.clear();
    } else {
      this.exportBox.style.display = 'none';
    }
    this.updateHint();
  }

  private updateHint(): void {
    this.hint.textContent =
      `EDYCJA MAPY — typ: ${this.currentType === 'tree' ? 'drzewo' : 'skała'}\n` +
      'klik: postaw   klik na postawionym: usuń\n' +
      'T/R: typ drzewo/skała   WASD: przesuń widok\n' +
      'kółko myszy: zoom   X: eksportuj   M: wyjście';
  }

  private onKeyDown = (e: KeyboardEvent): void => {
    const key = e.key.toLowerCase();
    if (key === 'm') {
      this.toggle();
      return;
    }
    if (!this.active) return;
    if (key === 'w' || key === 'a' || key === 's' || key === 'd') {
      e.preventDefault();
      this.panKeys.add(key);
    }
    if (key === 't') {
      e.preventDefault();
      this.currentType = 'tree';
      this.updateHint();
    }
    if (key === 'r') {
      e.preventDefault();
      this.currentType = 'rock';
      this.updateHint();
    }
    if (key === 'x') {
      e.preventDefault();
      this.showExport();
    }
  };

  private onKeyUp = (e: KeyboardEvent): void => {
    const key = e.key.toLowerCase();
    if (key === 'w' || key === 'a' || key === 's' || key === 'd') this.panKeys.delete(key);
  };

  private onWheel = (e: WheelEvent): void => {
    if (!this.active) return;
    e.preventDefault();
    this.cameraZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, this.cameraZoom + e.deltaY * 0.001));
  };

  private raycastGround(clientX: number, clientY: number): THREE.Vector3 | null {
    const rect = this.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((clientX - rect.left) / rect.width) * 2 - 1,
      -((clientY - rect.top) / rect.height) * 2 + 1,
    );
    this.raycaster.setFromCamera(ndc, this.camera);
    const hit = new THREE.Vector3();
    return this.raycaster.ray.intersectPlane(GROUND_PLANE, hit) ? hit : null;
  }

  private onPointerMove = (e: PointerEvent): void => {
    if (!this.active) return;
    const hit = this.raycastGround(e.clientX, e.clientY);
    this.preview.visible = hit !== null;
    if (hit) this.preview.position.set(hit.x, 0, hit.z);
  };

  private onPointerDown = (e: PointerEvent): void => {
    if (!this.active) return;
    const hit = this.raycastGround(e.clientX, e.clientY);
    if (!hit) return;

    const nearby = this.placed.find((p) => Math.hypot(p.obstacle.x - hit.x, p.obstacle.z - hit.z) <= PICK_RADIUS);
    if (nearby) {
      this.scene.remove(nearby.mesh);
      const oi = this.obstacles.indexOf(nearby.obstacle);
      if (oi >= 0) this.obstacles.splice(oi, 1);
      this.placed.splice(this.placed.indexOf(nearby), 1);
      return;
    }

    const radius = this.currentType === 'tree' ? 0.5 : 0.3 + Math.random() * 0.35;
    const obstacle: Obstacle = { type: this.currentType, x: hit.x, z: hit.z, radius };
    const mesh = this.buildGhost(this.currentType, false);
    mesh.position.set(hit.x, 0, hit.z);
    this.scene.add(mesh);
    this.obstacles.push(obstacle);
    this.placed.push({ obstacle, mesh });
  };

  private buildGhost(type: Obstacle['type'], ghostly = true): THREE.Group {
    const group = new THREE.Group();
    if (type === 'tree') {
      const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.2, 1.2, 6), this.trunkMat);
      trunk.position.y = 0.6;
      const foliage = new THREE.Mesh(new THREE.ConeGeometry(0.9, 2, 8), this.treeMat);
      foliage.position.y = 1.8;
      group.add(trunk, foliage);
    } else {
      const rock = new THREE.Mesh(new THREE.DodecahedronGeometry(0.4, 0), this.rockMat);
      rock.position.y = 0.25;
      group.add(rock);
    }
    if (ghostly) {
      group.traverse((obj) => {
        if ((obj as THREE.Mesh).isMesh) {
          const mesh = obj as THREE.Mesh;
          const mat = (mesh.material as THREE.MeshStandardMaterial).clone();
          mat.transparent = true;
          mat.opacity = 0.45;
          mesh.material = mat;
        }
      });
    }
    return group;
  }

  private showExport(): void {
    const lines = this.obstacles.map(
      (o) => `  { type: '${o.type}', x: ${o.x.toFixed(2)}, z: ${o.z.toFixed(2)}, radius: ${o.radius.toFixed(2)} },`,
    );
    this.exportBox.value =
      `// Wklej to do src/world/customLayout.ts, zastępując CUSTOM_OBSTACLES:\n` +
      `export const CUSTOM_OBSTACLES: Obstacle[] = [\n${lines.join('\n')}\n];\n`;
    this.exportBox.style.display = 'block';
    this.exportBox.focus();
    this.exportBox.select();
  }
}
