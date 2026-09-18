import { useEffect, useState, type CSSProperties } from 'react';
import { AlertTriangle, ExternalLink, ImageOff, Info, Microscope } from 'lucide-react';
import {
  pathologyClasses,
  pathologyClassKeys,
  type SlideManifest,
  type SlideRecord,
} from '../data/contracts';
import { useT, type Translate } from '../i18n';
import { useFormat } from '../format';
import { EmptyState } from './EmptyState';
import { ViewerFrame } from './ViewerFrame';

type Format = ReturnType<typeof useFormat>;
type TileGrid = NonNullable<SlideRecord['tileGrid']>;

/** Montaj gercekten o yerlesimde mi; uymayan bir sayfaya sira numarasi verilmez. */
export function gridFitsSheet(grid: TileGrid, width: number, height: number): boolean {
  return width === grid.columns * grid.tilePx && height === grid.rows * grid.tilePx;
}

function SlideImage({ src, alt }: { src: string; alt: string }) {
  const t = useT();
  const [failed, setFailed] = useState(false);
  if (failed)
    return (
      <EmptyState
        icon={<ImageOff />}
        title={t('pathology.imageFailed')}
        action={
          <button className="button" onClick={() => setFailed(false)}>
            {t('workspace.retry')}
          </button>
        }
      >
        {t('pathology.imageFailedBody')}
      </EmptyState>
    );
  return <img key={src} src={src} alt={alt} onError={() => setFailed(true)} />;
}

/** En yuksek attention'li kareler: paket yerlesimi soyluyorsa numarali izgara,
 *  soylemiyorsa (ya da dosya o yerlesime uymuyorsa) sayfanin kendisi. */
function TopTiles({ slide, t }: { slide: SlideRecord; t: Translate }) {
  const src = slide.assets.top_tiles;
  const grid = slide.tileGrid;
  const [shape, setShape] = useState<'grid' | 'sheet' | 'failed'>(grid ? 'grid' : 'sheet');
  useEffect(() => {
    if (!grid) return undefined;
    const probe = new Image();
    probe.onload = () =>
      setShape(gridFitsSheet(grid, probe.naturalWidth, probe.naturalHeight) ? 'grid' : 'sheet');
    probe.onerror = () => setShape('failed');
    probe.src = src;
    return () => {
      probe.onload = null;
      probe.onerror = null;
    };
  }, [src, grid]);
  const alt = t('pathology.topTilesAlt', { id: slide.id });
  if (shape === 'failed')
    return (
      <EmptyState icon={<ImageOff />} title={t('pathology.imageFailed')}>
        {t('pathology.imageFailedBody')}
      </EmptyState>
    );
  if (shape === 'sheet' || !grid)
    return <img className="tile-sheet" src={src} alt={alt} onError={() => setShape('failed')} />;
  return (
    <ol className="tile-grid" style={{ '--tile-columns': grid.columns } as CSSProperties}>
      {Array.from({ length: grid.count }, (_, index) => {
        const column = index % grid.columns;
        const row = Math.floor(index / grid.columns);
        return (
          <li key={index}>
            <span
              className="tile-cell"
              role="img"
              aria-label={t('pathology.tileRank', { rank: index + 1 })}
              style={{
                backgroundImage: `url("${src}")`,
                backgroundSize: `${grid.columns * 100}% ${grid.rows * 100}%`,
                backgroundPosition: `${grid.columns > 1 ? (column / (grid.columns - 1)) * 100 : 0}%
                  ${grid.rows > 1 ? (row / (grid.rows - 1)) * 100 : 0}%`,
              }}
            />
            <b aria-hidden="true">{index + 1}</b>
          </li>
        );
      })}
    </ol>
  );
}

/** Rapordaki vaka figurunun karar paneli: sinif, referans, olasiliklar ve top-2 farki. */
function Decision({
  slide,
  reviewMargin,
  ensemble,
  t,
  format,
}: {
  slide: SlideRecord;
  reviewMargin: number;
  ensemble: boolean;
  t: Translate;
  format: Format;
}) {
  const predicted = slide.prediction.class;
  const probabilities = slide.prediction.probabilities;
  const ranked = pathologyClasses.map((name) => probabilities[name]).sort((a, b) => b - a);
  const gap = ranked[0] - ranked[1];
  const locked = slide.split === 'test';
  const decidedBy = ensemble
    ? t('pathology.decisionEnsemble')
    : t('pathology.decisionSingle', { version: slide.modelVersion ?? '' });
  return (
    <section
      className="decision"
      data-tour="slide-prediction"
      aria-label={t('pathology.probabilities')}
    >
      <div className="decision-call">
        <span className="eyebrow">
          {t('pathology.decision')} · {decidedBy}
        </span>
        <h3>
          <i className={`class-dot class-${predicted}`} aria-hidden="true" />
          {t(pathologyClassKeys[predicted])}
        </h3>
        <strong className="decision-share">{format.score(probabilities[predicted])}</strong>
      </div>
      {slide.reference && (
        <div className="decision-reference">
          <span className="eyebrow">{t('pathology.referenceHeading')}</span>
          <strong>{t(pathologyClassKeys[slide.reference.class])}</strong>
          <span className={`outcome-pill ${slide.agreesWithReference ? 'correct' : 'wrong'}`}>
            {t(slide.agreesWithReference ? 'pathology.outcomeCorrect' : 'pathology.outcomeWrong')}
          </span>
        </div>
      )}
      <p className="slide-context">
        {t('pathology.grade')} {slide.whoGrade} · {slide.sourceSite} · {slide.source} ·{' '}
        {t(locked ? 'pathology.splitLocked' : 'pathology.splitValidation')} ·{' '}
        {t('pathology.tiles')} {format.count(slide.tilesUsed)}
      </p>
      {/* Yanlis siniflanan vaka bir ariza degil; sonuc olarak yaziliyor. */}
      {slide.reference && !slide.agreesWithReference && (
        <p className="decision-note">{t('pathology.disagreesBody')}</p>
      )}
      {!locked && <p className="decision-note">{t('pathology.splitValidationNote')}</p>}
      <ul className="probability-list">
        {pathologyClasses.map((name) => (
          <li key={name} className={name === predicted ? 'predicted' : ''}>
            <span className="probability-name">
              <i className={`class-dot class-${name}`} aria-hidden="true" />
              {t(pathologyClassKeys[name])}
              {slide.reference?.class === name && (
                <span className="reference-mark" role="img" aria-label={t('pathology.referenceMark')}>
                  ◆
                </span>
              )}
            </span>
            <span className="probability-bar" aria-hidden="true">
              <i
                className={`class-fill class-${name}`}
                style={{ width: `${probabilities[name] * 100}%` }}
              />
            </span>
            <strong>{format.score(probabilities[name])}</strong>
          </li>
        ))}
      </ul>
      {/* Cekimserlik kurali gizli bir esik degil: pay, esik ve esigin olculmus
          sinirlari birlikte yaziliyor. */}
      <div className="margin-meter">
        <div className="margin-head">
          <span className="eyebrow">{t('pathology.gap')}</span>
          <span className={`margin-pill ${slide.needsExpertReview ? 'below' : 'above'}`}>
            {t(slide.needsExpertReview ? 'pathology.gapBelow' : 'pathology.gapAbove')}
          </span>
        </div>
        <div className="margin-track">
          <i className="margin-fill" style={{ width: `${Math.min(gap, 1) * 100}%` }} />
          <i className="margin-threshold" style={{ left: `${reviewMargin * 100}%` }} />
        </div>
        <p>
          {t('pathology.gapBody', {
            margin: format.score(gap),
            threshold: format.score(reviewMargin, 2),
          })}
        </p>
        <p className="margin-limit">{t('pathology.gapLimit')}</p>
      </div>
      {slide.needsExpertReview && (
        <section className="flag-band" aria-label={t('pathology.review')}>
          <h3>
            <AlertTriangle size={16} /> {t('pathology.review')}
          </h3>
          <p>{t('pathology.reviewBody', { margin: format.score(reviewMargin, 2) })}</p>
        </section>
      )}
    </section>
  );
}

/** Rapordaki (b) paneli: harita ne gosterir, ne gostermez. */
function MapReading({
  slide,
  ensemble,
  t,
  format,
}: {
  slide: SlideRecord;
  ensemble: boolean;
  t: Translate;
  format: Format;
}) {
  const attention = slide.attention;
  return (
    <section className="map-reading panel" aria-label={t('pathology.mapReading')}>
      <h3>{t('pathology.mapReading')}</h3>
      <div className="heat-scale" aria-hidden="true">
        <span>{t('pathology.heatLow')}</span>
        <i />
        <span>{t('pathology.heatHigh')}</span>
      </div>
      <p className="map-caption">
        {t('pathology.mapCaption', {
          tiles: format.count(attention?.tilesEvaluated ?? slide.tilesUsed),
          scale: t(
            attention?.scale === 'within_slide_percentile'
              ? 'pathology.scalePercentile'
              : 'pathology.scaleRaw',
          ),
        })}
      </p>
      <ul className="map-notes">
        <li>{t('pathology.mapNotSegmentation')}</li>
        <li>{t('pathology.mapNotFinding')}</li>
        <li>{t('pathology.mapIsAttention')}</li>
      </ul>
      {attention?.scale !== 'within_slide_percentile' && (
        <p className="map-limit">{t('pathology.mapRawNote')}</p>
      )}
      {attention && (
        <p className="map-limit">
          {t('pathology.attentionFrom', {
            version: attention.modelVersion,
            decision: ensemble
              ? t('pathology.decisionEnsemble')
              : t('pathology.decisionSingle', { version: slide.modelVersion ?? '' }),
          })}
        </p>
      )}
    </section>
  );
}

export function PathologyWorkspace({
  slide,
  model,
  reviewMargin,
}: {
  slide: SlideRecord;
  model: SlideManifest['model'];
  reviewMargin: number;
}) {
  const t = useT();
  const format = useFormat();
  const grid = slide.tileGrid;
  const ensemble = slide.predictionSource
    ? slide.predictionSource === 'ensemble_cv_v1'
    : model.ensemble;
  const concentration = slide.attentionConcentration;
  return (
    <div className="pathology-module">
      <Decision
        slide={slide}
        reviewMargin={reviewMargin}
        ensemble={ensemble}
        t={t}
        format={format}
      />
      <div className="slide-row">
        <ViewerFrame title={t('pathology.mapTitle')} icon={<Microscope size={18} />} tour="slide-viewer">
          <div className="slide-stage">
            <div className="slide-meta">
              <span>{slide.id}</span>
              <strong>{t('cases.slideModality')}</strong>
            </div>
            {/* Ham agirlik renderi neredeyse hicbir sey gostermez; goruntunun
                kendisi bunu soylemezse ekran onu raporun figuru gibi sunar. */}
            {slide.attention?.scale !== 'within_slide_percentile' && (
              <span className="slide-warning">{t('pathology.mapRawBadge')}</span>
            )}
            <SlideImage
              src={slide.assets.attention}
              alt={t('pathology.slideAlt', { id: slide.id })}
            />
          </div>
        </ViewerFrame>
        <MapReading slide={slide} ensemble={ensemble} t={t} format={format} />
      </div>
      <section className="tiles-panel panel" aria-label={t('pathology.topTiles')}>
        <div className="panel-heading">
          <span>{t('pathology.tilesHeading')}</span>
          {grid && (
            <small>
              {t('pathology.tileScale', {
                px: grid.tilePx,
                mpp: format.score(grid.micronsPerPixel, 1),
                microns: format.count(Math.round(grid.tilePx * grid.micronsPerPixel)),
              })}
            </small>
          )}
        </div>
        <TopTiles slide={slide} t={t} />
        {grid && <p className="tiles-note">{t('pathology.tileOrder')}</p>}
      </section>
      <section className="slide-statistics panel" aria-label={t('pathology.attentionSpread')}>
        <p className="statistics-note">
          <Info size={15} /> {t('pathology.concentrationNote')}
        </p>
        <dl>
          <div>
            <dt>{t('pathology.top1')}</dt>
            <dd>{format.percent(concentration.top1Share)}</dd>
          </div>
          <div>
            <dt>{t('pathology.top10')}</dt>
            <dd>{format.percent(concentration.top10Share)}</dd>
          </div>
          <div>
            <dt>{t('pathology.entropy')}</dt>
            <dd>{format.score(concentration.entropyNormalised, 2)}</dd>
          </div>
        </dl>
      </section>
      <p className="model-note">
        <span className="eyebrow">{t('pathology.modelNote')}</span>{' '}
        {t(ensemble ? 'pathology.modelEnsemble' : 'pathology.modelSingle', {
          version: slide.modelVersion ?? model.version,
        })}
        {slide.assets.report && (
          <a href={slide.assets.report} target="_blank" rel="noreferrer noopener">
            {t('pathology.report')} <ExternalLink size={13} />
          </a>
        )}
      </p>
    </div>
  );
}
