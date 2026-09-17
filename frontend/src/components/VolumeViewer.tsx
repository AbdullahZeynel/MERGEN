import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RotateCcw, Box } from 'lucide-react';
import { parseMesh, regions, type Region } from '../data/mesh';
import { EmptyState } from './EmptyState';
import { useT } from '../i18n';
import type { MessageKey } from '../i18n/messages';

const colors = { ET: 0xff596c, TC_NCR: 0x57cea2, ED: 0x599eee, BRAIN: 0xe2e8f0 };
const labelKeys: Record<Region, MessageKey> = {
  ET: 'mesh.ET',
  TC_NCR: 'mesh.TC_NCR',
  ED: 'mesh.ED',
  BRAIN: 'mesh.BRAIN',
};
export function VolumeViewer({ url }: { url?: string }) {
  const t = useT();
  const host = useRef<HTMLDivElement>(null);
  const sceneControl = useRef<{ group: THREE.Group; draw: () => void; reset: () => void } | null>(
    null,
  );
  const [state, setState] = useState('loading');
  const [attempt, setAttempt] = useState(0);
  const [available, setAvailable] = useState<Region[]>([]);
  const [visible, setVisible] = useState<Record<Region, boolean>>({
    ET: true,
    TC_NCR: true,
    ED: true,
    BRAIN: true,
  });
  const [opacity, setOpacity] = useState(75);
  useEffect(() => {
    if (!url || !host.current) {
      setState('missing');
      return;
    }
    const element = host.current;
    const controller = new AbortController();
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setState('webgl');
      return;
    }
    setState('loading');
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    element.appendChild(renderer.domElement);
    renderer.domElement.setAttribute('aria-label', t('mesh.canvas'));
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 10000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = false;
    const group = new THREE.Group();
    scene.add(group, new THREE.HemisphereLight(0xffffff, 0x34415c, 2));
    const light = new THREE.DirectionalLight(0xffffff, 2.5);
    light.position.set(100, 150, 200);
    scene.add(light);
    const draw = () => renderer.render(scene, camera);
    const reset = () => {
      if (!group.children.length) return;
      const box = new THREE.Box3().setFromObject(group);
      const center = box.getCenter(new THREE.Vector3());
      const radius = box.getSize(new THREE.Vector3()).length() / 2;
      const angle = Math.min(
        (camera.fov * Math.PI) / 360,
        Math.atan(Math.tan((camera.fov * Math.PI) / 360) * camera.aspect),
      );
      const distance = (radius / Math.sin(angle)) * 1.15;
      camera.position
        .copy(center)
        .add(new THREE.Vector3(1, 0.65, 1).normalize().multiplyScalar(distance));
      controls.target.copy(center);
      controls.minDistance = radius * 0.3;
      controls.maxDistance = distance * 6;
      camera.near = Math.max(radius / 1000, 0.01);
      camera.far = distance * 20;
      camera.updateProjectionMatrix();
      controls.update();
      draw();
    };
    const resize = new ResizeObserver(() => {
      const { width, height } = element.getBoundingClientRect();
      if (!width || !height) return;
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      draw();
    });
    resize.observe(element);
    controls.addEventListener('change', draw);
    const lost = (event: Event) => {
      event.preventDefault();
      setState('webgl');
    };
    renderer.domElement.addEventListener('webglcontextlost', lost);
    sceneControl.current = { group, draw, reset };
    const addGeometry = (region: Region, geometry: THREE.BufferGeometry) => {
      if (!geometry.getAttribute('normal')) geometry.computeVertexNormals();
      const material = new THREE.MeshPhongMaterial({
        color: colors[region],
        transparent: true,
        opacity: region === 'BRAIN' ? 0.12 : opacity / 100,
        side: THREE.DoubleSide,
        depthWrite: false,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.userData.region = region;
      group.add(mesh);
    };
    fetch(url, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error('mesh-request-failed');
        const found = new Set<Region>();
        if (url.endsWith('.glb')) {
          const payload = await response.arrayBuffer();
          const loaded = await new Promise<THREE.Group>((resolve, reject) => {
            new GLTFLoader().parse(payload, '', (gltf) => resolve(gltf.scene), reject);
          });
          loaded.traverse((object) => {
            if (!(object instanceof THREE.Mesh)) return;
            const candidate = object.userData.region ?? object.name ?? object.parent?.name;
            if (!regions.includes(candidate as Region) || found.has(candidate as Region)) return;
            const region = candidate as Region;
            found.add(region);
            addGeometry(region, object.geometry);
            const sourceMaterials = Array.isArray(object.material)
              ? object.material
              : [object.material];
            sourceMaterials.forEach((material) => material.dispose());
          });
        } else {
          const meshes = parseMesh(await response.json());
          for (const region of regions) {
            const data = meshes[region];
            if (!data) continue;
            found.add(region);
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute(
              'position',
              new THREE.Float32BufferAttribute(data.vertices.flat(), 3),
            );
            geometry.setIndex(data.faces.flat());
            addGeometry(region, geometry);
          }
        }
        return [...found];
      })
      .then((found) => {
        if (controller.signal.aborted || !found) return;
        if (!found.length) {
          // Paket okundu ama gosterilecek bolge yok: modelin bu vakada bulgu
          // bildirmedigi anlamina gelir. Yukleme hatasi gibi sunmak, basarili
          // bir analizi basarisiz gostermek olurdu.
          setState('none');
          return;
        }
        setAvailable(found);
        const { width, height } = element.getBoundingClientRect();
        renderer.setSize(width, height);
        camera.aspect = width / Math.max(height, 1);
        reset();
        setState('ready');
      })
      .catch(() => {
        if (!controller.signal.aborted) setState('error');
      });
    return () => {
      controller.abort();
      resize.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener('webglcontextlost', lost);
      group.children.forEach((object) => {
        const mesh = object as THREE.Mesh<THREE.BufferGeometry, THREE.Material>;
        mesh.geometry.dispose();
        mesh.material.dispose();
      });
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
      sceneControl.current = null;
    };
  }, [url, attempt]);
  useEffect(() => {
    const control = sceneControl.current;
    if (!control) return;
    control.group.children.forEach((object) => {
      const mesh = object as THREE.Mesh<THREE.BufferGeometry, THREE.MeshPhongMaterial>;
      mesh.visible = visible[mesh.userData.region as Region];
      mesh.material.opacity = mesh.userData.region === 'BRAIN' ? 0.12 : opacity / 100;
    });
    control.draw();
  }, [visible, opacity, state]);
  return (
    <>
      <div className="mesh-stage">
        <div className="mesh-canvas" ref={host} />
        {state !== 'ready' && (
          <div className="mesh-message" role="status">
            <EmptyState
              icon={<Box />}
              title={
                state === 'loading'
                  ? t('mesh.loading')
                  : state === 'none'
                    ? t('mesh.noRegions')
                    : state === 'missing'
                      ? t('mesh.missing')
                      : state === 'webgl'
                        ? t('mesh.webglFailed')
                        : t('mesh.failed')
              }
              action={
                state !== 'loading' && state !== 'missing' && state !== 'none' ? (
                  <button className="button" onClick={() => setAttempt((a) => a + 1)}>
                    {t('workspace.retry')}
                  </button>
                ) : undefined
              }
            >
              {state === 'webgl'
                ? t('mesh.webglHint')
                : state === 'loading'
                  ? t('mesh.loadingHint')
                  : state === 'none'
                    ? t('mesh.noRegionsHint')
                    : t('mesh.fallbackHint')}
            </EmptyState>
          </div>
        )}
        <span className="mesh-hint">{t('mesh.navHint')}</span>
      </div>
      <div className="mesh-controls">
        <div className="region-buttons">
          {regions.map((region) => (
            <button
              key={region}
              className={`region-${region}`}
              disabled={state !== 'ready' || !available.includes(region)}
              title={
                region === 'BRAIN' ? t('mesh.brainTitle') : t(labelKeys[region])
              }
              aria-pressed={visible[region]}
              onClick={() => setVisible((v) => ({ ...v, [region]: !v[region] }))}
            >
              <i />
              {t(labelKeys[region])}
            </button>
          ))}
          <button
            className="icon-button"
            aria-label={t('mesh.resetCamera')}
            disabled={state !== 'ready'}
            onClick={() => sceneControl.current?.reset()}
          >
            <RotateCcw size={17} />
          </button>
        </div>
        <label>
          {t('mesh.opacity')}{' '}
          <input
            type="range"
            min="10"
            max="100"
            value={opacity}
            disabled={state !== 'ready'}
            onChange={(e) => setOpacity(Number(e.target.value))}
          />
          {opacity}%
        </label>
      </div>
    </>
  );
}
