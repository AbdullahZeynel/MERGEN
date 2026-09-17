import { useState } from 'react';
import { AlertTriangle, ExternalLink, ImageOff, Info, Layers, Microscope } from 'lucide-react';
import {
  pathologyClasses,
  pathologyClassKeys,
  type SlideManifest,
  type SlideRecord,
} from '../data/contracts';
import { useT } from '../i18n';
import { useFormat } from '../format';
import { EmptyState } from './EmptyState';
import { ViewerFrame } from './ViewerFrame';

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
  const predicted = slide.prediction.class;
  const probabilities = slide.prediction.probabilities;
  return (
    <>
      <div className="imaging-grid">
        <ViewerFrame title={t('pathology.slide')} icon={<Microscope size={18} />} tour="slide-viewer">
          <div className="image-stage">
            <div className="image-meta">
              <span>{slide.id}</span>
              <strong>{t('cases.slideModality')}</strong>
            </div>
            <SlideImage src={slide.assets.attention} alt={t('pathology.slideAlt', { id: slide.id })} />
          </div>
        </ViewerFrame>
        <ViewerFrame title={t('pathology.topTiles')} icon={<Layers size={18} />} tour="tiles-viewer">
          <div className="image-stage">
            <SlideImage
              src={slide.assets.top_tiles}
              alt={t('pathology.topTilesAlt', { id: slide.id })}
            />
          </div>
        </ViewerFrame>
      </div>
      <div className="notice">
        <Info size={16} />
        <span>{t('pathology.notice')}</span>
      </div>
      <section
        className="panel prediction-panel"
        data-tour="slide-prediction"
        aria-label={t('pathology.probabilities')}
      >
        <div className="prediction-head">
          <div>
            <span className="eyebrow">{t('pathology.predicted')}</span>
            <strong>{t(pathologyClassKeys[predicted])}</strong>
          </div>
          {slide.reference && (
            <div className="prediction-reference">
              <span className="eyebrow">{t('pathology.referenceLabel')}</span>
              <strong>{t(pathologyClassKeys[slide.reference.class])}</strong>
              <span className={`agreement-pill ${slide.agreesWithReference ? 'agrees' : 'disagrees'}`}>
                {t(slide.agreesWithReference ? 'pathology.agrees' : 'pathology.disagrees')}
              </span>
            </div>
          )}
        </div>
        {/* Yanlis siniflanan vaka bir ariza degil; sonuc olarak yaziliyor. */}
        {slide.reference && !slide.agreesWithReference && (
          <p className="prediction-note">{t('pathology.disagreesBody')}</p>
        )}
        <ul className="probability-list">
          {pathologyClasses.map((name) => (
            <li key={name} className={name === predicted ? 'predicted' : ''}>
              <span>{t(pathologyClassKeys[name])}</span>
              <span className="probability-bar" aria-hidden="true">
                <i style={{ width: `${Math.round(probabilities[name] * 100)}%` }} />
              </span>
              <strong>{format.percent(probabilities[name])}</strong>
            </li>
          ))}
        </ul>
        {slide.needsExpertReview && (
          <section className="flag-band" aria-label={t('pathology.review')}>
            <h3>
              <AlertTriangle size={16} /> {t('pathology.review')}
            </h3>
            <p>{t('pathology.reviewBody', { margin: format.score(reviewMargin, 2) })}</p>
          </section>
        )}
        <div className="attention-stats">
          <span className="eyebrow">{t('pathology.attentionSpread')}</span>
          <dl>
            <div>
              <dt>{t('pathology.top1')}</dt>
              <dd>{format.percent(slide.attentionConcentration.top1Share)}</dd>
            </div>
            <div>
              <dt>{t('pathology.top10')}</dt>
              <dd>{format.percent(slide.attentionConcentration.top10Share)}</dd>
            </div>
            <div>
              <dt>{t('pathology.entropy')}</dt>
              <dd>{format.score(slide.attentionConcentration.entropyNormalised, 2)}</dd>
            </div>
            <div>
              <dt>{t('pathology.tiles')}</dt>
              <dd>{format.count(slide.tilesUsed)}</dd>
            </div>
          </dl>
        </div>
      </section>
      <section className="case-details pathology-details panel">
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
    </>
  );
}
