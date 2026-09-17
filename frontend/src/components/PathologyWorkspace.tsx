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

function Decision({
  slide,
  reviewMargin,
  t,
  format,
}: {
  slide: SlideRecord;
  reviewMargin: number;
  t: Translate;
  format: Format;
}) {
  const predicted = slide.prediction.class;
  const probabilities = slide.prediction.probabilities;
  const ranked = pathologyClasses.map((name) => probabilities[name]).sort((a, b) => b - a);
  const margin = ranked[0] - ranked[1];
  return (
    <section className="decision" data-tour="slide-prediction" aria-label={t('pathology.probabilities')}>
      <div className="decision-call">
        <span className="eyebrow">{t('pathology.predicted')}</span>
        <h3>
          <i className={`class-dot class-${predicted}`} aria-hidden="true" />
          {t(pathologyClassKeys[predicted])}
        </h3>
        <strong className="decision-share">{format.percent(probabilities[predicted])}</strong>
      </div>
      {slide.reference && (
        <div className="decision-reference">
          <span className="eyebrow">{t('pathology.referenceLabel')}</span>
          <strong>{t(pathologyClassKeys[slide.reference.class])}</strong>
          <span className={`agreement-pill ${slide.agreesWithReference ? 'agrees' : 'disagrees'}`}>
            {t(slide.agreesWithReference ? 'pathology.agrees' : 'pathology.disagrees')}
          </span>
        </div>
      )}
      {/* Yanlis siniflanan vaka bir ariza degil; sonuc olarak yaziliyor. */}
      {slide.reference && !slide.agreesWithReference && (
        <p className="decision-note">{t('pathology.disagreesBody')}</p>
      )}
      <ul className="probability-list">
        {pathologyClasses.map((name) => (
          <li key={name} className={name === predicted ? 'predicted' : ''}>
            <span className="probability-name">
              <i className={`class-dot class-${name}`} aria-hidden="true" />
              {t(pathologyClassKeys[name])}
            </span>
            <span className="probability-bar" aria-hidden="true">
              <i
                className={`class-fill class-${name}`}
                style={{ width: `${probabilities[name] * 100}%` }}
              />
            </span>
            <strong>{format.percent(probabilities[name])}</strong>
          </li>
        ))}
      </ul>
      {/* Cekimserlik kurali gizli bir esik degil: pay da esik de cizilir. */}
      <div className="margin-meter">
        <div className="margin-head">
          <span className="eyebrow">{t('pathology.margin')}</span>
          <span className={`margin-pill ${slide.needsExpertReview ? 'below' : 'above'}`}>
            {t(slide.needsExpertReview ? 'pathology.marginBelow' : 'pathology.marginAbove')}
          </span>
        </div>
        <div className="margin-track">
          <i className="margin-fill" style={{ width: `${Math.min(margin, 1) * 100}%` }} />
          <i className="margin-threshold" style={{ left: `${reviewMargin * 100}%` }} />
        </div>
        <p>
          {t('pathology.marginBody', {
            margin: format.score(margin, 2),
            threshold: format.score(reviewMargin, 2),
          })}
        </p>
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

function Attention({
  slide,
  t,
  format,
}: {
  slide: SlideRecord;
  t: Translate;
  format: Format;
}) {
  const { top1Share, top10Share, entropyNormalised } = slide.attentionConcentration;
  return (
    <section className="attention-card panel" aria-label={t('pathology.attentionSpread')}>
      <h3>{t('pathology.attentionSpread')}</h3>
      <div className="heat-scale" aria-hidden="true">
        <span>{t('pathology.heatLow')}</span>
        <i />
        <span>{t('pathology.heatHigh')}</span>
      </div>
      <p className="heat-note">
        <span className="sr-only">{t('pathology.heatScale')}: </span>
        {t('pathology.heatBody')}
      </p>
      <dl>
        <div>
          <dt>{t('pathology.top1')}</dt>
          <dd>{format.percent(top1Share)}</dd>
        </div>
        <div>
          <dt>{t('pathology.top10')}</dt>
          <dd>{format.percent(top10Share)}</dd>
        </div>
        <div>
          <dt>{t('pathology.entropy')}</dt>
          <dd>{format.score(entropyNormalised, 2)}</dd>
        </div>
        <div>
          <dt>{t('pathology.tiles')}</dt>
          <dd>{format.count(slide.tilesUsed)}</dd>
        </div>
      </dl>
      {slide.tilesUsed > 10 && (
        <p className="attention-read">
          {t('pathology.top10Body', {
            share: format.percent(top10Share),
            rest: format.count(slide.tilesUsed - 10),
          })}
        </p>
      )}
      <div className="notice">
        <Info size={16} />
        <span>{t('pathology.notice')}</span>
      </div>
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
  return (
    <div className="pathology-module">
      <Decision slide={slide} reviewMargin={reviewMargin} t={t} format={format} />
      <div className="slide-row">
        <ViewerFrame title={t('pathology.slide')} icon={<Microscope size={18} />} tour="slide-viewer">
          <div className="slide-stage">
            <div className="slide-meta">
              <span>{slide.id}</span>
              <strong>{t('cases.slideModality')}</strong>
            </div>
            <SlideImage
              src={slide.assets.attention}
              alt={t('pathology.slideAlt', { id: slide.id })}
            />
          </div>
        </ViewerFrame>
        <Attention slide={slide} t={t} format={format} />
      </div>
      <section className="tiles-panel panel" aria-label={t('pathology.topTiles')}>
        <div className="panel-heading">
          <span>{t('pathology.topTiles')}</span>
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
      <section className="slide-facts panel">
        <div>
          <span className="eyebrow">{t('pathology.patient')}</span>
          <strong>{slide.patientId}</strong>
        </div>
        <div>
          <span className="eyebrow">{t('case.sourceEyebrow')}</span>
          <strong>{slide.source}</strong>
        </div>
        <div>
          <span className="eyebrow">{t('pathology.site')}</span>
          <strong>{slide.sourceSite}</strong>
        </div>
        <div>
          <span className="eyebrow">{t('pathology.grade')}</span>
          <strong>{slide.whoGrade}</strong>
        </div>
        <div>
          <span className="eyebrow">{t('pathology.split')}</span>
          <strong>{slide.split}</strong>
        </div>
      </section>
      {/* Manifestin kendi notu paketin dilinde yazili; ekran ayni olguyu
          kendi sozlugunden, model surumunu veri olarak koyarak yaziyor. */}
      <p className="model-note">
        <span className="eyebrow">{t('pathology.modelNote')}</span>{' '}
        {t(model.ensemble ? 'pathology.modelEnsemble' : 'pathology.modelSingle', {
          version: model.version,
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
