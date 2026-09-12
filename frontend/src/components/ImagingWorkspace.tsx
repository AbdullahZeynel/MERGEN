import { useState } from 'react';
import { Box, ImageOff, ScanLine, Info } from 'lucide-react';
import { axes, axisLabels, type Axis, type CaseRecord } from '../data/contracts';
import { EmptyState } from './EmptyState';
import { ViewerFrame } from './ViewerFrame';
import { VolumeViewer } from './VolumeViewer';

export function ImagingWorkspace({ record }: { record: CaseRecord }) {
  const [axis, setAxis] = useState<Axis>('axial');
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const preview = record.previews.find((p) => p.axis === axis)!;
  return (
    <>
      <div className="imaging-grid">
        <ViewerFrame title="2D kesit önizlemesi" icon={<ScanLine size={18} />}>
          <div className="image-stage">
            <div className="image-meta">
              <span>{record.id}</span>
              <strong>FLAIR</strong>
            </div>
            {failedSrc === preview.src ? (
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
                key={preview.src}
                src={preview.src}
                onError={() => setFailedSrc(preview.src)}
                alt={`${record.id} FLAIR ${axisLabels[axis]} önizleme, kesit ${preview.index + 1}`}
              />
            )}
            <div className="image-caption">
              <span>{axisLabels[axis]}</span>
              <span>
                Kesit {preview.index + 1} /{' '}
                {record.shape[{ axial: 2, coronal: 1, sagittal: 0 }[axis]]}
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
            <span className="muted small">Hazır merkez kesit</span>
          </div>
        </ViewerFrame>
        <ViewerFrame title="3D segmentasyon" icon={<Box size={18} />}>
          <VolumeViewer url={record.mesh} />
        </ViewerFrame>
      </div>
      <div className="notice">
        <Info size={16} />
        <span>
          Hazır FLAIR merkez kesitleri ve ensemble segmentasyonu gösteriliyor. Serbest 2D kesit
          gezinmesi henüz bağlı değil.
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
