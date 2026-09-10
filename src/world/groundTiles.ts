import * as THREE from 'three';

/** A flat ground decal cropped from the uploaded path/water tile sheets — a plane laid
 * directly on the ground (unlike props.ts's upright billboards), used for paths, streams,
 * and other walkable/passable terrain dressing that has no collision. */
export interface GroundTileDef {
  id: string;
  texture: string;
  /** World-unit footprint, precomputed from the source crop's own pixel aspect ratio. */
  width: number;
  depth: number;
}

/** Rendered slightly larger than the 2.2-unit placement grid — the source crops have a bit
 * of irregular grass padding baked in around the connectable dirt/water core (they weren't
 * drawn as a perfectly seamless tileset), so a small overlap hides the seam a flush edge-to-
 * edge size would leave between tiles. */
export const GROUND_TILES: Record<string, GroundTileDef> = {
  pathStraight: { id: 'pathStraight', texture: '/tiles/path-straight.png', width: 2.6, depth: 2.6 },
  pathCorner: { id: 'pathCorner', texture: '/tiles/path-corner.png', width: 2.6, depth: 2.6 },
  grassPatch: { id: 'grassPatch', texture: '/tiles/grass-patch.png', width: 2.6, depth: 2.6 },
  waterStraight: { id: 'waterStraight', texture: '/tiles/water-straight.png', width: 2.6, depth: 2.6 * (170 / 256) },
  waterCorner: { id: 'waterCorner', texture: '/tiles/water-corner.png', width: 2.6, depth: 2.6 * (170 / 256) },
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

/** rotationDeg spins the tile in its own plane (around its normal) before laying it flat,
 * so the same straight/corner art can point whichever way a path segment needs. */
export function createGroundTile(tileId: string, rotationDeg = 0): THREE.Mesh {
  const def = GROUND_TILES[tileId];
  const geometry = new THREE.PlaneGeometry(def.width, def.depth);
  const material = new THREE.MeshStandardMaterial({
    map: getTexture(def.texture),
    transparent: true,
    alphaTest: 0.3,
    roughness: 1,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.rotation.set(-Math.PI / 2, 0, THREE.MathUtils.degToRad(rotationDeg));
  mesh.receiveShadow = true;
  return mesh;
}
