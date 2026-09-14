#!/usr/bin/env node
// Compare legacy JSON parsing/geometry creation with GLB loading outside rendering.
import { readFile, readdir } from 'node:fs/promises';
import { performance } from 'node:perf_hooks';
import { resolve } from 'node:path';
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const [jsonRootArg, glbRootArg, ...caseIds] = process.argv.slice(2);
if (!jsonRootArg || !glbRootArg || !caseIds.length) {
  console.error('usage: benchmark_meshes.mjs <json-cases-root> <glb-cases-root> <case-id>...');
  process.exit(2);
}
const jsonRoot = resolve(jsonRootArg);
const glbRoot = resolve(glbRootArg);
const regions = ['ET', 'TC_NCR', 'ED', 'BRAIN'];
const median = (values) => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];

function dispose(group) {
  group.traverse((object) => {
    if (!object.isMesh) return;
    object.geometry.dispose();
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    materials.forEach((material) => material.dispose());
  });
}

function parseJson(text) {
  const value = JSON.parse(text);
  const group = new THREE.Group();
  for (const region of regions) {
    const item = value[region];
    if (!item) continue;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(item.vertices.flat(), 3));
    geometry.setIndex(item.faces.flat());
    geometry.computeVertexNormals();
    group.add(new THREE.Mesh(geometry, new THREE.MeshBasicMaterial()));
  }
  return group;
}

function parseGlb(buffer) {
  const payload = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
  return new Promise((resolveLoad, reject) => {
    new GLTFLoader().parse(payload, '', (gltf) => {
      gltf.scene.traverse((object) => {
        if (object.isMesh && !object.geometry.getAttribute('normal')) {
          object.geometry.computeVertexNormals();
        }
      });
      resolveLoad(gltf.scene);
    }, reject);
  });
}

console.log('case json_bytes glb_bytes reduction json_p50_ms glb_p50_ms');
for (const caseId of caseIds) {
  if (!/^[A-Za-z0-9._-]+$/.test(caseId)) throw new Error('invalid case ID');
  const jsonPath = resolve(jsonRoot, caseId, 'mesh_ensemble.json');
  const glbNames = (await readdir(resolve(glbRoot, caseId))).filter((name) => /^mesh-[0-9a-f]{64}\.glb$/.test(name));
  if (glbNames.length !== 1) throw new Error(`expected one GLB for ${caseId}`);
  const [jsonBuffer, glbBuffer] = await Promise.all([
    readFile(jsonPath),
    readFile(resolve(glbRoot, caseId, glbNames[0])),
  ]);
  const jsonText = jsonBuffer.toString('utf8');
  const jsonTimes = [];
  const glbTimes = [];
  for (let run = 0; run < 11; run += 1) {
    let start = performance.now();
    const jsonGroup = parseJson(jsonText);
    const jsonTime = performance.now() - start;
    dispose(jsonGroup);
    start = performance.now();
    const glbGroup = await parseGlb(glbBuffer);
    const glbTime = performance.now() - start;
    dispose(glbGroup);
    if (run) {
      jsonTimes.push(jsonTime);
      glbTimes.push(glbTime);
    }
  }
  const reduction = 100 * (1 - glbBuffer.byteLength / jsonBuffer.byteLength);
  console.log([
    caseId,
    jsonBuffer.byteLength,
    glbBuffer.byteLength,
    reduction.toFixed(1),
    median(jsonTimes).toFixed(2),
    median(glbTimes).toFixed(2),
  ].join(' '));
}
