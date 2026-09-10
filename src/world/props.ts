import * as THREE from 'three';

/** A billboard world prop cut from the uploaded isometric art sheets. Rendered as a
 * THREE.Sprite, which always faces the camera — since the game's camera angle never
 * rotates (GDD Section 28's fixed-camera design), a single flat sprite reads correctly
 * from every position, the same trick classic isometric RPGs used for trees/props. */
export interface PropDef {
  id: string;
  texture: string;
  /** World-unit size, precomputed from the source crop's own pixel aspect ratio. */
  width: number;
  height: number;
  /** Collision radius (Obstacle.radius) — usually smaller than the visual width. */
  radius: number;
}

export const PROPS: Record<string, PropDef> = {
  oakTree: { id: 'oakTree', texture: '/props/oak-tree.png', width: 2.55, height: 3.2, radius: 0.6 },
  smallTree: { id: 'smallTree', texture: '/props/small-tree.png', width: 1.44, height: 2.0, radius: 0.4 },
  mossyRock: { id: 'mossyRock', texture: '/props/mossy-rock.png', width: 1.18, height: 1.0, radius: 0.5 },
};

const loader = new THREE.TextureLoader();
const textureCache = new Map<string, THREE.Texture>();

function getTexture(path: string): THREE.Texture {
  let texture = textureCache.get(path);
  if (!texture) {
    texture = loader.load(path);
    texture.colorSpace = THREE.SRGBColorSpace;
    textureCache.set(path, texture);
  }
  return texture;
}

/** Anchors the sprite's bottom-center to `sprite.position` (not the default middle-center),
 * so placing it at (x, 0, z) sits it on the ground like the tree/rock meshes it sits beside. */
export function createPropSprite(propId: string, opacity = 1): THREE.Sprite {
  const def = PROPS[propId];
  const material = new THREE.SpriteMaterial({
    map: getTexture(def.texture),
    transparent: true,
    alphaTest: 0.4,
    opacity,
  });
  const sprite = new THREE.Sprite(material);
  sprite.center.set(0.5, 0);
  sprite.scale.set(def.width, def.height, 1);
  return sprite;
}
