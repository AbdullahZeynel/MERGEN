import { useEffect, useRef } from 'react';
import { ExternalLink, ShieldCheck, X } from 'lucide-react';
import { useT } from '../i18n';

const DATASET_DOI = 'https://doi.org/10.7937/tcia.bdgf-8v37';
const PAPER_DOI = 'https://doi.org/10.1148/ryai.220058';
const COLLECTION = 'https://www.cancerimagingarchive.net/collection/ucsf-pdgm/';
const SUBTYPE_DOI = 'https://doi.org/10.1016/j.cell.2015.12.028';
const WEIGHTS_DOI = 'https://doi.org/10.5281/zenodo.11582627';

/** Veri kaynagi, kimliksizlestirme ve atiflar. Icerik ATTRIBUTIONS.md'yi yansitir. */
export function AboutDialog({ onClose }: { onClose: () => void }) {
  const t = useT();
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = overflow;
      element?.close();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className="about-dialog"
      aria-labelledby="about-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === dialog.current) onClose();
      }}
    >
      <div className="about-body">
        <div className="about-head">
          <h2 id="about-title">
            <ShieldCheck size={20} /> {t('about.title')}
          </h2>
          <button className="icon-button" aria-label={t('about.close')} onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <section aria-labelledby="privacy-heading">
          <h3 id="privacy-heading">{t('privacy.heading')}</h3>
          <p className="about-lead">{t('privacy.lead')}</p>
          <ul className="about-list">
            <li>{t('privacy.consent')}</li>
            <li>{t('privacy.skullStripped')}</li>
            <li>{t('privacy.noUpload')}</li>
            <li>{t('privacy.licence')}</li>
          </ul>
          <p className="about-clinical">{t('privacy.clinical')}</p>
        </section>

        <section aria-labelledby="credits-heading">
          <h3 id="credits-heading">{t('credits.heading')}</h3>

          <h4>{t('credits.datasetTitle')}</h4>
          <p>{t('credits.datasetBody')}</p>
          <blockquote>
            {t('credits.datasetCitation')}{' '}
            <a href={DATASET_DOI} target="_blank" rel="noreferrer noopener">
              {DATASET_DOI} <ExternalLink size={13} />
            </a>
          </blockquote>
          <blockquote>
            {t('credits.paperCitation')}{' '}
            <a href={PAPER_DOI} target="_blank" rel="noreferrer noopener">
              {PAPER_DOI} <ExternalLink size={13} />
            </a>
          </blockquote>
          <p>
            <a href={COLLECTION} target="_blank" rel="noreferrer noopener">
              {t('credits.collection')} <ExternalLink size={13} />
            </a>{' '}
            · CC BY 4.0
          </p>

          <h4>{t('credits.modelsTitle')}</h4>
          <p>{t('credits.modelsBody')}</p>

          <h4>{t('credits.pathologyTitle')}</h4>
          <p>{t('credits.pathologyBody')}</p>
          <blockquote>
            {t('credits.pathologyCitation')}{' '}
            <a href={SUBTYPE_DOI} target="_blank" rel="noreferrer noopener">
              {SUBTYPE_DOI} <ExternalLink size={13} />
            </a>
          </blockquote>

          <h4>{t('credits.encoderTitle')}</h4>
          <p>{t('credits.encoderBody')}</p>

          <h4>{t('credits.weightsTitle')}</h4>
          <p>{t('credits.weightsBody')}</p>
          <p>
            <a href={WEIGHTS_DOI} target="_blank" rel="noreferrer noopener">
              {WEIGHTS_DOI} <ExternalLink size={13} />
            </a>{' '}
            · CC BY 4.0
          </p>

          <h4>{t('credits.licenceTitle')}</h4>
          <p>{t('credits.licenceBody')}</p>
          <p className="about-note">{t('credits.full')}</p>
        </section>
      </div>
    </dialog>
  );
}
