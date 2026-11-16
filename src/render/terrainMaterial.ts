import * as THREE from 'three';

export interface TerrainDetailOptions {
  /** kachelbare Fels-Helligkeit (Graustufen um 50 %) */
  detail: THREE.Texture;
  /** Kachelgroesse in Metern */
  tileSize?: number;
  /** Rand des Datenausschnitts (Spielkoordinaten x/z): dort in den Dunst ausblenden */
  bounds?: { minX: number; maxX: number; minZ: number; maxZ: number };
  /** Breite der Ausblendzone am Rand (m) */
  edgeFade?: number;
  edgeColor?: THREE.Color;
  /** Staerke der Detail-Normalen (0 = aus) */
  bump?: number;
  /** Staerke der Detail-Helligkeit (0 = aus) */
  albedo?: number;
}

/**
 * Erweitert ein MeshStandardMaterial (Luftbild-Textur) um:
 *  - triplanare Fels-Detailtextur, nur auf dunklen (Fels-)Bereichen und nur in der Naehe
 *  - feine Detail-Normalen (Bump aus der Detailtextur), steile Flaechen staerker
 *  - Schnee: helle Bereiche leicht glaenzend (geringere Rauheit)
 *  - Ausblenden zum Rand des Datenausschnitts (fehlendes Italien) in die Dunstfarbe
 */
export function applyTerrainDetail(mat: THREE.MeshStandardMaterial, o: TerrainDetailOptions): void {
  const t = o.detail;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.generateMipmaps = true;
  t.minFilter = THREE.LinearMipmapLinearFilter;
  t.anisotropy = 8;
  t.colorSpace = THREE.NoColorSpace;
  const b = o.bounds ?? { minX: -1e9, maxX: 1e9, minZ: -1e9, maxZ: 1e9 };
  const uniforms = {
    uDetail: { value: t },
    uTile: { value: 1 / (o.tileSize ?? 3.5) },
    uBounds: { value: new THREE.Vector4(b.minX, b.maxX, b.minZ, b.maxZ) },
    uEdgeFade: { value: o.edgeFade ?? 900 },
    uEdgeColor: { value: o.edgeColor ?? new THREE.Color(0xc4d2e2) },
    uBump: { value: o.bump ?? 0 }, // Bump aus Ableitungen flimmert sichtbar -> vorerst aus (?bump=0.25 zum Testen)
    uAlbedo: { value: o.albedo ?? 1 },
  };

  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace(
        '#include <common>',
        `#include <common>
         varying vec3 vDetailPos;
         varying vec3 vDetailNormal;`,
      )
      .replace(
        '#include <worldpos_vertex>',
        `#include <worldpos_vertex>
         vDetailPos = (modelMatrix * vec4(transformed, 1.0)).xyz;
         vDetailNormal = normalize(mat3(modelMatrix) * objectNormal);`,
      );

    shader.fragmentShader = shader.fragmentShader
      .replace(
        '#include <common>',
        `#include <common>
         uniform sampler2D uDetail;
         uniform float uTile;
         uniform vec4 uBounds;
         uniform float uEdgeFade;
         uniform vec3 uEdgeColor;
         uniform float uBump;
         uniform float uAlbedo;
         varying vec3 vDetailPos;
         varying vec3 vDetailNormal;
         float gDetail = 0.5;
         float gSnow = 0.0;
         float gNear = 0.0;
         float gBumpH = 0.5;
         float triDetail(vec3 p, vec3 n) {
           vec3 w = pow(abs(n), vec3(4.0));
           w /= (w.x + w.y + w.z);
           float a = texture2D(uDetail, p.zy * uTile).r;
           float b2 = texture2D(uDetail, p.xz * uTile).r;
           float c = texture2D(uDetail, p.xy * uTile).r;
           // zweite, groebere Ebene gegen sichtbares Kachelmuster
           float big = texture2D(uDetail, p.xz * uTile * 0.17 + 0.37).r;
           return (a * w.x + b2 * w.y + c * w.z) * 0.75 + big * 0.25;
         }`,
      )
      .replace(
        '#include <map_fragment>',
        `#include <map_fragment>
         {
           float dist = length(vDetailPos - cameraPosition);
           gNear = 1.0 - smoothstep(25.0, 260.0, dist);
           vec3 n = normalize(vDetailNormal);
           float lum = dot(diffuseColor.rgb, vec3(0.299, 0.587, 0.114));
           gSnow = smoothstep(0.42, 0.72, lum);           // hell im Luftbild = Schnee/Firn
           float steep = 1.0 - smoothstep(0.45, 0.8, n.y); // steil = Fels
           float rock = max(1.0 - gSnow, steep * 0.6);
           gDetail = triDetail(vDetailPos, n);
           // fuer den Bump eine ruhigere, groebere Variante (nur wenn Bump aktiv ist)
           if (uBump > 0.0) gBumpH = triDetail(vDetailPos * 0.35, n);
           float k = gNear * mix(0.12, 0.7, rock) * uAlbedo;
           // Steile Flaechen in der Naehe: das von oben aufgenommene Luftbild ist dort verzerrt.
           // Stattdessen Fels-Fotostruktur mit der gemittelten Farbe der Umgebung (unscharfe Mip-Stufe).
           float steepNear = (1.0 - smoothstep(0.38, 0.62, n.y)) * (1.0 - smoothstep(80.0, 450.0, dist)) * uAlbedo;
           vec3 avg = texture2D(map, vMapUv, 6.0).rgb;
           avg = mix(avg, vec3(dot(avg, vec3(0.333))), 0.55);         // entsaettigt (kein Blaustich)
           avg = clamp(avg, vec3(0.08), vec3(0.45));                   // Fels, kein Schnee/Schatten-Schwarz
           vec3 rockCol = avg * gDetail * 2.0;
           diffuseColor.rgb *= mix(1.0, gDetail * 2.0, k * (1.0 - steepNear));
           diffuseColor.rgb = mix(diffuseColor.rgb, rockCol, steepNear);
         }`,
      )
      .replace(
        '#include <roughnessmap_fragment>',
        `#include <roughnessmap_fragment>
         roughnessFactor = mix(roughnessFactor, 0.5, gSnow * 0.85);  // Schnee leicht glaenzend`,
      )
      .replace(
        '#include <normal_fragment_maps>',
        `#include <normal_fragment_maps>
         {
           // Bump aus der Detailtextur (Ableitungen im Bildraum)
           vec3 dpdx = dFdx(-vViewPosition);
           vec3 dpdy = dFdy(-vViewPosition);
           float h = gBumpH * gNear * mix(0.15, 1.0, 1.0 - gSnow);
           float dhdx = dFdx(h);
           float dhdy = dFdy(h);
           vec3 r1 = cross(dpdy, normal);
           vec3 r2 = cross(normal, dpdx);
           float fDet = dot(dpdx, r1);
           vec3 grad = sign(fDet) * (dhdx * r1 + dhdy * r2);
           normal = normalize(abs(fDet) * normal - grad * uBump);
         }`,
      )
      .replace(
        '#include <fog_fragment>',
        `{
           float e = min(min(vDetailPos.x - uBounds.x, uBounds.y - vDetailPos.x),
                         min(vDetailPos.z - uBounds.z, uBounds.w - vDetailPos.z));
           float f = 1.0 - smoothstep(0.0, uEdgeFade, e);
           gl_FragColor.rgb = mix(gl_FragColor.rgb, uEdgeColor, f * 0.92);
         }
         #include <fog_fragment>`,
      );
  };
  mat.customProgramCacheKey = () => 'terrain-detail-v1';
  mat.needsUpdate = true;
}
