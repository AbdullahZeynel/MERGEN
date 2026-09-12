import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RotateCcw, Box } from 'lucide-react';
import { parseMesh, regions, type Region } from '../data/mesh';
import { EmptyState } from './EmptyState';

const colors = { ET: 0xff596c, TC_NCR: 0x57cea2, ED: 0x599eee };
const labels = { ET: 'ET', TC_NCR: 'NCR', ED: 'Ödem' };
export function VolumeViewer({ url }: { url?: string }) {
  const host = useRef<HTMLDivElement>(null);
  const sceneControl = useRef<{ group: THREE.Group; draw: () => void; reset: () => void } | null>(
    null,
  );
  const [state, setState] = useState('loading');
  const [attempt, setAttempt] = useState(0);
  const [visible, setVisible] = useState<Record<Region, boolean>>({
    ET: true,
    TC_NCR: true,
    ED: true,
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
    renderer.domElement.setAttribute('aria-label', 'Etkileşimli 3D tümör modeli');
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
    fetch(url, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('Mesh yüklenemedi');
        return response.json();
      })
      .then((value) => {
        if (controller.signal.aborted) return;
        const meshes = parseMesh(value);
        for (const region of regions) {
          const data = meshes[region];
          if (!data) continue;
          const geometry = new THREE.BufferGeometry();
          geometry.setAttribute(
            'position',
            new THREE.Float32BufferAttribute(data.vertices.flat(), 3),
          );
          geometry.setIndex(data.faces.flat());
          geometry.computeVertexNormals();
          const material = new THREE.MeshPhongMaterial({
            color: colors[region],
            transparent: true,
            opacity: 0.75,
            side: THREE.DoubleSide,
            depthWrite: false,
          });
          const mesh = new THREE.Mesh(geometry, material);
          mesh.userData.region = region;
          group.add(mesh);
        }
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
      mesh.material.opacity = opacity / 100;
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
                  ? '3D model yükleniyor…'
                  : state === 'missing'
                    ? '3D sonuç paketi bulunamadı'
                    : state === 'webgl'
                      ? '3D görüntüleme başlatılamadı'
                      : '3D model yüklenemedi'
              }
              action={
                state !== 'loading' && state !== 'missing' ? (
                  <button className="button" onClick={() => setAttempt((a) => a + 1)}>
                    Yeniden dene
                  </button>
                ) : undefined
              }
            >
              {state === 'webgl'
                ? 'Tarayıcının WebGL desteğini ve donanım hızlandırmasını kontrol edin.'
                : state === 'loading'
                  ? 'Hazır segmentasyon verisi açılıyor.'
                  : 'Vakanın 2D görüntülerini incelemeye devam edebilirsiniz.'}
            </EmptyState>
          </div>
        )}
        <span className="mesh-hint">Sürükle: döndür · Tekerlek: yakınlaştır · Sağ tuş: taşı</span>
      </div>
      <div className="mesh-controls">
        <div className="region-buttons">
          {regions.map((region) => (
            <button
              key={region}
              className={`region-${region}`}
              disabled={state !== 'ready'}
              aria-pressed={visible[region]}
              onClick={() => setVisible((v) => ({ ...v, [region]: !v[region] }))}
            >
              <i />
              {labels[region]}
            </button>
          ))}
          <button
            className="icon-button"
            aria-label="3D kamerayı sıfırla"
            disabled={state !== 'ready'}
            onClick={() => sceneControl.current?.reset()}
          >
            <RotateCcw size={17} />
          </button>
        </div>
        <label>
          Opaklık{' '}
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
