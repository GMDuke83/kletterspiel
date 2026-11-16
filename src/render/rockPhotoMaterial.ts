import * as THREE from 'three';

export interface RockPhotoTextures {
  /** Helligkeit um 50 % (Fels-Foto ohne Farbe) */
  detail: THREE.Texture;
  /** Normal-Map (OpenGL) */
  normal: THREE.Texture;
  /** Rauheit */
  rough: THREE.Texture;
}

/**
 * Legt die Fels-Fototextur (Poly Haven "Rock Face 03", CC0) als Detail auf ein Wand-Material:
 * Helligkeit wird multipliziert (Farbe bleibt die gebackene Wandfarbe), die Foto-Normalen werden
 * mit der gebackenen Normal-Map gemischt, die Rauheit kommt aus dem Foto.
 * repeat = wie oft die Kachel ueber die Wand-UVs (0..1) wiederholt wird.
 */
export function applyRockPhoto(
  mat: THREE.MeshStandardMaterial,
  tex: RockPhotoTextures,
  repeat: THREE.Vector2,
  strength = 1,
): void {
  for (const t of [tex.detail, tex.normal, tex.rough]) {
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.anisotropy = 8;
  }
  tex.detail.colorSpace = THREE.NoColorSpace;
  tex.normal.colorSpace = THREE.NoColorSpace;
  tex.rough.colorSpace = THREE.NoColorSpace;
  const uniforms = {
    uRockDetail: { value: tex.detail },
    uRockNormal: { value: tex.normal },
    uRockRough: { value: tex.rough },
    uRockRepeat: { value: repeat },
    uRockAmt: { value: strength },
  };
  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.fragmentShader = shader.fragmentShader
      .replace(
        '#include <common>',
        `#include <common>
         uniform sampler2D uRockDetail;
         uniform sampler2D uRockNormal;
         uniform sampler2D uRockRough;
         uniform vec2 uRockRepeat;
         uniform float uRockAmt;`,
      )
      .replace(
        '#include <map_fragment>',
        `#include <map_fragment>
         diffuseColor.rgb *= mix(1.0, texture2D(uRockDetail, vMapUv * uRockRepeat).r * 2.0, 0.85 * uRockAmt);`,
      )
      .replace(
        '#include <roughnessmap_fragment>',
        `#include <roughnessmap_fragment>
         roughnessFactor = mix(roughnessFactor, 0.55 + 0.45 * texture2D(uRockRough, vMapUv * uRockRepeat).r, 0.8 * uRockAmt);`,
      )
      .replace(
        'mapN.xy *= normalScale;',
        `mapN.xy *= normalScale;
         {
           // Foto-Normalen ueberlagern (UDN-Mischung)
           vec3 dN = texture2D(uRockNormal, vNormalMapUv * uRockRepeat).xyz * 2.0 - 1.0;
           mapN = normalize(vec3(mapN.xy + dN.xy * 1.2 * uRockAmt, mapN.z));
         }`,
      );
  };
  mat.customProgramCacheKey = () => 'rock-photo-v1';
  mat.needsUpdate = true;
}
