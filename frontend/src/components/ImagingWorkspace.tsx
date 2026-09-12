import { useState } from 'react';
import { Box, ImageOff, ScanLine, Info } from 'lucide-react';
import { axes, axisLabels, type Axis, type CaseRecord } from '../data/contracts';
import { EmptyState } from './EmptyState';
import { ViewerFrame } from './ViewerFrame';
import { VolumeViewer } from './VolumeViewer';

export function ImagingWorkspace({ record }: { record: CaseRecord }) {
  const [axis, setAxis] = useState<Axis>('axial');
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const [indices, setIndices] = useState(
    () => Object.fromEntries(record.previews.map((p) => [p.axis, p.index])) as Record<Axis, number>,
  );
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null);
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
            <div className="image-caption">
              <span>{axisLabels[axis]}</span>
              <span>
                Kesit {index + 1} / {count}
                {loadedSrc !== src && failedSrc !== src ? ' · Yükleniyor…' : ''}
              </span>
            </div>
          </div>
          <div className="viewer-controls">
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
          <VolumeViewer url={record.mesh} />
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
