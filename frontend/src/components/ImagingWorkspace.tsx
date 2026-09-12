import { useState } from 'react';
import { Box, ImageOff, Layers, ScanLine, Expand, Minimize, Info } from 'lucide-react';
import { axes, axisLabels, type Axis, type CaseRecord } from '../data/contracts';
import { EmptyState } from './EmptyState';

export function ImagingWorkspace({ record }: { record: CaseRecord }) {
  const [axis, setAxis] = useState<Axis>('axial');
  const [expanded, setExpanded] = useState(false);
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const preview = record.previews.find((p) => p.axis === axis)!;
  return (
    <>
      <div className={`imaging-grid ${expanded ? 'is-expanded' : ''}`}>
        <section className="viewer panel" aria-label="2D MR önizlemesi">
          <div className="panel-heading">
            <span>
              <ScanLine size={18} /> 2D kesit önizlemesi
            </span>
            <button
              className="icon-button"
              onClick={() => setExpanded(!expanded)}
              aria-label={expanded ? 'Görüntüyü küçült' : 'Görüntüyü genişlet'}
              aria-pressed={expanded}
            >
              {expanded ? <Minimize size={17} /> : <Expand size={17} />}
            </button>
          </div>
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
        </section>
        {!expanded && (
          <section className="panel volume-panel" aria-label="3D görüntüleme alanı">
            <div className="panel-heading">
              <span>
                <Box size={18} /> 3D segmentasyon
              </span>
              <span className="small muted">Hazırlanıyor</span>
            </div>
            <EmptyState icon={<Box size={36} strokeWidth={1.2} />} title="Hacim görünümü">
              Etkileşimli 3D model ve bölge katmanları görüntüleyici entegrasyonu tamamlandığında
              burada yer alacak.
            </EmptyState>
            <div className="volume-foot">
              <Layers size={16} />
              <span>Ensemble · bölgesel segmentasyon</span>
            </div>
          </section>
        )}
      </div>
      <div className="notice">
        <Info size={16} />
        <span>
          Önceden hazırlanmış FLAIR kesitleri gösteriliyor. Kesit gezinme ve segmentasyon
          kontrolleri henüz bağlı değil.
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
