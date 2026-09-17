import { useEffect, useState } from 'react';
import { Box, ImageOff, ScanLine, Info } from 'lucide-react';
import { axes, axisKeys, type Axis, type CaseRecord } from '../data/contracts';
import { useT } from '../i18n';
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
  const t = useT();
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
        <ViewerFrame title={t('viewer.slices')} icon={<ScanLine size={18} />} tour="slice-viewer">
          <div
            className="image-stage"
            tabIndex={0}
            aria-label={t('viewer.stage')}
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
                title={t('viewer.sliceFailed')}
                action={
                  <button className="button" onClick={() => setFailedSrc(null)}>
                    {t('workspace.retry')}
                  </button>
                }
              >
                {t('viewer.sliceFailedBody')}
              </EmptyState>
            ) : (
              <img
                key={src}
                src={src}
                style={{ visibility: loadedSrc === src ? 'visible' : 'hidden' }}
                onLoad={() => setLoadedSrc(src)}
                onError={() => setFailedSrc(src)}
                alt={t('viewer.sliceAlt', {
                  id: record.id,
                  axis: t(axisKeys[axis]),
                  index: index + 1,
                })}
              />
            )}
            {record.overlays?.includes('prediction') && predictionVisible && (
              <img
                className="slice-overlay"
                src={`/api/demo/cases/${record.id}/overlays/prediction/${axis}/${index}`}
                alt={t('viewer.predictionAlt')}
              />
            )}
            {record.overlays?.includes('ground_truth') && groundTruthVisible && (
              <img
                className="slice-overlay"
                src={`/api/demo/cases/${record.id}/overlays/ground_truth/${axis}/${index}`}
                alt={t('viewer.groundTruthAlt')}
              />
            )}
            <div className="image-caption">
              <span>{t(axisKeys[axis])}</span>
              <span>
                {t('viewer.sliceOf', { index: index + 1, count })}
                {loadedSrc !== src && failedSrc !== src ? ` · ${t('viewer.loadingShort')}` : ''}
              </span>
            </div>
          </div>
          <div className="viewer-controls">
            {record.overlays && (
              <div className="overlay-controls" data-tour="overlay-controls" aria-label={t('viewer.overlays')}>
                <button
                  aria-pressed={predictionVisible}
                  onClick={() => setPredictionVisible(!predictionVisible)}
                >
                  <i className="prediction-dot" /> {t('viewer.prediction')}
                </button>
                <button
                  aria-pressed={groundTruthVisible}
                  onClick={() => setGroundTruthVisible(!groundTruthVisible)}
                >
                  <i className="ground-truth-dot" /> {t('viewer.groundTruth')}
                </button>
              </div>
            )}
            <div className="segmented" aria-label={t('viewer.plane')}>
              {axes.map((a) => (
                <button
                  key={a}
                  aria-pressed={axis === a}
                  className={axis === a ? 'selected' : ''}
                  onClick={() => setAxis(a)}
                >
                  {t(axisKeys[a])}
                </button>
              ))}
            </div>
            <div className="slice-navigation">
              <button
                className="button"
                aria-label={t('viewer.previousSlice')}
                disabled={index === 0}
                onClick={() => move(index - 1)}
              >
                −
              </button>
              <label>
                {t('viewer.sliceOf', { index: index + 1, count })}
                <input
                  aria-label={t('viewer.pickSlice')}
                  type="range"
                  min={1}
                  max={count}
                  value={index + 1}
                  onChange={(e) => move(Number(e.target.value) - 1)}
                />
              </label>
              <button
                className="button"
                aria-label={t('viewer.nextSlice')}
                disabled={index === count - 1}
                onClick={() => move(index + 1)}
              >
                +
              </button>
              <button className="button" onClick={() => move(Math.floor(count / 2))}>
                {t('viewer.centre')}
              </button>
            </div>
            <p className="slice-hint">{t('viewer.keyboardHint')}</p>
          </div>
        </ViewerFrame>
        <ViewerFrame title={t('viewer.mesh')} icon={<Box size={18} />} tour="mesh-viewer">
          <LazyVolumeViewer url={record.mesh} />
        </ViewerFrame>
      </div>
      <div className="notice">
        <Info size={16} />
        <span>
          {t('case.notice')}
          {record.brainContext && ` ${t('case.brainNotice')}`}
        </span>
      </div>
      <section className="case-details panel">
        <div>
          <span className="eyebrow">{t('case.sourceEyebrow')}</span>
          <strong>{record.source}</strong>
        </div>
        <div>
          <span className="eyebrow">{t('case.shapeEyebrow')}</span>
          <strong>
            {record.shape.join(' × ')} <small>{t('case.voxel')}</small>
          </strong>
        </div>
        <div>
          <span className="eyebrow">{t('case.previewEyebrow')}</span>
          <strong>{t('case.previewValue')}</strong>
        </div>
        <div>
          <span className="eyebrow">{t('case.resultEyebrow')}</span>
          <strong>{t('cases.demo')}</strong>
        </div>
      </section>
    </>
  );
}
