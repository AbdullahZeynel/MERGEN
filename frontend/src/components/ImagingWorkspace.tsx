import { useEffect, useState } from 'react';
import { Box, ImageOff, ScanLine, Info } from 'lucide-react';
import { axes, axisLabels, type Axis, type CaseRecord } from '../data/contracts';
import { EmptyState } from './EmptyState';
import { LazyVolumeViewer } from './LazyVolumeViewer';
import { ViewerFrame } from './ViewerFrame';

export function ImagingWorkspace({
  record,
  nextMeshUrl,
}: {
  record: CaseRecord;
  nextMeshUrl?: string;
}) {
  const [axis, setAxis] = useState<Axis>('axial');
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const [indices, setIndices] = useState(
    () => Object.fromEntries(record.previews.map((p) => [p.axis, p.index])) as Record<Axis, number>,
  );
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null);
  const [predictionVisible, setPredictionVisible] = useState(true);
  const [groundTruthVisible, setGroundTruthVisible] = useState(false);
  useEffect(() => {
    if (!nextMeshUrl?.endsWith('.glb')) return;
    const controller = new AbortController();
    let idle: number | undefined;
    const timeout = window.setTimeout(() => {
      const prefetch = () => {
        void fetch(nextMeshUrl, { cache: 'force-cache', signal: controller.signal }).catch(() => {});
      };
      if ('requestIdleCallback' in window) idle = window.requestIdleCallback(prefetch, { timeout: 2000 });
      else prefetch();
    }, 2500);
    return () => {
      window.clearTimeout(timeout);
      if (idle !== undefined && 'cancelIdleCallback' in window) window.cancelIdleCallback(idle);
      controller.abort();
    };
  }, [nextMeshUrl]);
  const count = record.shape[{ axial: 2, coronal: 1, sagittal: 0 }[axis]];
  const index = indices[axis];
  const src = `/api/demo/cases/${record.id}/slices/${axis}/${index}`;
  const move = (value: number) =>
    setIndices((prev) => ({ ...prev, [axis]: Math.max(0, Math.min(count - 1, value)) }));
  return (
    <>
      <div className="imaging-grid">
        <ViewerFrame title="2D kesit görüntüleyici" icon={<ScanLine size={18} />}>
          <div
            className="image-stage"
            tabIndex={0}
            aria-label="Kesit görüntüsü; ok tuşlarıyla gezin"
            onKeyDown={(event) => {
              if (['ArrowUp', 'ArrowRight', 'ArrowDown', 'ArrowLeft'].includes(event.key)) {
                event.preventDefault();
                move(index + (['ArrowUp', 'ArrowRight'].includes(event.key) ? 1 : -1));
              }
            }}
          >
            <div className="image-meta">
              <span>{record.id}</span>
              <strong>FLAIR</strong>
            </div>
            {failedSrc === src ? (
              <EmptyState
                icon={<ImageOff />}
                title="Kesit görüntüsü yüklenemedi"
                action={
                  <button className="button" onClick={() => setFailedSrc(null)}>
                    Yeniden dene
                  </button>
                }
              >
                Vakanın diğer düzlemlerini görüntüleyebilirsiniz.
              </EmptyState>
            ) : (
              <img
                key={src}
                src={src}
                style={{ visibility: loadedSrc === src ? 'visible' : 'hidden' }}
                onLoad={() => setLoadedSrc(src)}
                onError={() => setFailedSrc(src)}
                alt={`${record.id} FLAIR ${axisLabels[axis]}, kesit ${index + 1}`}
              />
            )}
            {record.overlays?.includes('prediction') && predictionVisible && (
              <img
                className="slice-overlay"
                src={`/api/demo/cases/${record.id}/overlays/prediction/${axis}/${index}`}
                alt="Ensemble tahmin maskesi"
              />
            )}
            {record.overlays?.includes('ground_truth') && groundTruthVisible && (
              <img
                className="slice-overlay"
                src={`/api/demo/cases/${record.id}/overlays/ground_truth/${axis}/${index}`}
                alt="Referans segmentasyon maskesi"
              />
            )}
            <div className="image-caption">
              <span>{axisLabels[axis]}</span>
              <span>
                Kesit {index + 1} / {count}
                {loadedSrc !== src && failedSrc !== src ? ' · Yükleniyor…' : ''}
              </span>
            </div>
          </div>
          <div className="viewer-controls">
            {record.overlays && (
              <div className="overlay-controls" aria-label="Segmentasyon katmanları">
                <button
                  aria-pressed={predictionVisible}
                  onClick={() => setPredictionVisible(!predictionVisible)}
                >
                  <i className="prediction-dot" /> Tahmin
                </button>
                <button
                  aria-pressed={groundTruthVisible}
                  onClick={() => setGroundTruthVisible(!groundTruthVisible)}
                >
                  <i className="ground-truth-dot" /> Referans
                </button>
              </div>
            )}
            <div className="segmented" aria-label="Görüntü düzlemi">
              {axes.map((a) => (
                <button
                  key={a}
                  aria-pressed={axis === a}
                  className={axis === a ? 'selected' : ''}
                  onClick={() => setAxis(a)}
                >
                  {axisLabels[a]}
                </button>
              ))}
            </div>
            <div className="slice-navigation">
              <button
                className="button"
                aria-label="Önceki kesit"
                disabled={index === 0}
                onClick={() => move(index - 1)}
              >
                −
              </button>
              <label>
                Kesit {index + 1} / {count}
                <input
                  aria-label="Kesit seç"
                  type="range"
                  min={1}
                  max={count}
                  value={index + 1}
                  onChange={(e) => move(Number(e.target.value) - 1)}
                />
              </label>
              <button
                className="button"
                aria-label="Sonraki kesit"
                disabled={index === count - 1}
                onClick={() => move(index + 1)}
              >
                +
              </button>
              <button className="button" onClick={() => move(Math.floor(count / 2))}>
                Merkez
              </button>
            </div>
          </div>
        </ViewerFrame>
        <ViewerFrame title="3D segmentasyon" icon={<Box size={18} />}>
          <LazyVolumeViewer url={record.mesh} />
        </ViewerFrame>
      </div>
      <div className="notice">
        <Info size={16} />
        <span>
          Hazır FLAIR kesitleri ve ensemble segmentasyonu VPS demo arşivinden MCP üzerinden sunulur.
          {record.brainContext &&
            ' Beyin dış yüzeyi MR ön planından yaklaşık olarak üretildi; korteks segmentasyonu değildir.'}
          {' Kesit alanına odaklanıp ok tuşlarıyla da gezinebilirsiniz.'}
        </span>
      </div>
      <section className="case-details panel">
        <div>
          <span className="eyebrow">VERİ KAYNAĞI</span>
          <strong>{record.source}</strong>
        </div>
        <div>
          <span className="eyebrow">HACİM BOYUTU</span>
          <strong>
            {record.shape.join(' × ')} <small>voxel</small>
          </strong>
        </div>
        <div>
          <span className="eyebrow">MEVCUT ÖNİZLEME</span>
          <strong>FLAIR · 3 düzlem</strong>
        </div>
        <div>
          <span className="eyebrow">SONUÇ TÜRÜ</span>
          <strong>Hazır demo</strong>
        </div>
      </section>
    </>
  );
}
