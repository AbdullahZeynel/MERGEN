import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BarChart3, RefreshCw, X } from 'lucide-react';
import { regions, regionKeys, type FigureRecord } from '../data/contracts';
import { lockedTest, type Interval, type LockedTest } from '../data/metrics';
import { listValidationFigures } from '../data/source';
import { useT, type Translate } from '../i18n';
import { useFormat } from '../format';
import { ReviewFlagBand } from './ReviewFlagBand';

type Format = ReturnType<typeof useFormat>;

function IntervalCells({ interval, format }: { interval: Interval; format: Format }) {
  return (
    <>
      <td>
        <strong>{format.score(interval.value)}</strong>
      </td>
      <td>
        {format.score(interval.low)} – {format.score(interval.high)}
      </td>
    </>
  );
}

function MetricTable({
  label,
  rows,
  t,
  format,
}: {
  label: string;
  rows: { key: string; label: string; interval: Interval }[];
  t: Translate;
  format: Format;
}) {
  return (
    <table className="metric-table" aria-label={label}>
      <thead>
        <tr>
          <th scope="col">{t('validation.metric')}</th>
          <th scope="col">{t('validation.value')}</th>
          <th scope="col">{t('validation.ci')}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key}>
            <th scope="row">{row.label}</th>
            <IntervalCells interval={row.interval} format={format} />
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Raporun sinif bazli tablosu: ortalamanin arkasindaki uc satir. Makro-F1
 *  tek basina hangi sinifin zorlandigini soylemez; bu tablo soyler. */
function PerClassTable({
  rows,
  t,
  format,
}: {
  rows: LockedTest['pathology']['perClass'];
  t: Translate;
  format: Format;
}) {
  const names = {
    A: 'validation.classShortA',
    O: 'validation.classShortO',
    G: 'validation.classShortG',
  } as const;
  return (
    <table className="metric-table per-class-table" aria-label={t('validation.perClassHeading')}>
      <thead>
        <tr>
          <th scope="col">{t('validation.class')}</th>
          <th scope="col">{t('validation.classCases')}</th>
          <th scope="col">{t('validation.precision')}</th>
          <th scope="col">{t('validation.recall')}</th>
          <th scope="col">{t('validation.f1')}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.class}>
            <th scope="row">
              <i className={`class-dot class-${row.class}`} aria-hidden="true" />
              {t(names[row.class])}
            </th>
            <td>{format.count(row.n)}</td>
            <td>{format.score(row.precision)}</td>
            <td>{format.score(row.recall)}</td>
            <td>
              <strong>{format.score(row.f1)}</strong>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Figure({ figure, t, format }: { figure: FigureRecord; t: Translate; format: Format }) {
  const reference = figure.regionVolumes?.reference;
  const prediction = figure.regionVolumes?.prediction;
  const score = (value: number | null | undefined, digits: number) =>
    typeof value === 'number' ? format.score(value, digits) : t('validation.notMeasured');
  return (
    <article className="validation-figure">
      <img src={figure.figure} alt={t('validation.figureAlt', { id: figure.id })} loading="lazy" />
      <div className="validation-figure-body">
        <h4>{figure.id}</h4>
        <p>
          <span className="eyebrow">{t('validation.reason')}</span> {figure.selectionReason}
        </p>
        <table className="metric-table" aria-label={figure.id}>
          <thead>
            <tr>
              <th scope="col">{t('validation.metric')}</th>
              {regions.map((region) => (
                <th key={region} scope="col">
                  <abbr title={t(regionKeys[region])}>{region}</abbr>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {reference && (
              <tr>
                <th scope="row">
                  {t('validation.volumes')} · {t('validation.reference')}
                </th>
                {regions.map((region) => (
                  <td key={region}>{format.count(reference[region])}</td>
                ))}
              </tr>
            )}
            {prediction && (
              <tr>
                <th scope="row">
                  {t('validation.volumes')} · {t('validation.prediction')}
                </th>
                {regions.map((region) => (
                  <td key={region}>{format.count(prediction[region])}</td>
                ))}
              </tr>
            )}
            {figure.dice && (
              <tr>
                <th scope="row">{t('validation.dice')}</th>
                {regions.map((region) => (
                  <td key={region}>{score(figure.dice?.[region], 3)}</td>
                ))}
              </tr>
            )}
            {figure.hd95Mm && (
              <tr>
                <th scope="row">{t('validation.hd95')}</th>
                {regions.map((region) => (
                  <td key={region}>{score(figure.hd95Mm?.[region], 2)}</td>
                ))}
              </tr>
            )}
          </tbody>
        </table>
        <ReviewFlagBand flags={figure.reviewFlags} />
        <p className="about-note">
          <span className="eyebrow">{t('validation.rule')}</span> {figure.ruleVersion} ·{' '}
          {figure.modelId} {figure.modelVersion}
        </p>
      </div>
    </article>
  );
}

/** Kilitli test sayilari, uc uyari ve olculmus ornek vakalar bir arada. */
export function ValidationDialog({ onClose }: { onClose: () => void }) {
  const t = useT();
  const format = useFormat();
  const dialog = useRef<HTMLDialogElement>(null);
  const figures = useQuery({
    queryKey: ['validation-figures'],
    queryFn: ({ signal }) => listValidationFigures(signal),
  });
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
  const { segmentation, pathology } = lockedTest;
  const diceRows = [
    ...regions.map((region) => ({
      key: region,
      label: `${t('validation.dice')} · ${t(regionKeys[region])}`,
      interval: segmentation.dice[region],
    })),
    {
      key: 'Mean',
      label: `${t('validation.dice')} · ${t('validation.mean')}`,
      interval: segmentation.dice.Mean,
    },
  ];
  const pathologyRows = (
    [
      ['macroF1', 'validation.macroF1'],
      ['balancedAccuracy', 'validation.balancedAccuracy'],
      ['auroc', 'validation.auroc'],
      ['mcc', 'validation.mcc'],
    ] as const
  ).map(([key, label]) => ({
    key,
    label: t(label),
    interval: pathology.metrics[key],
  }));
  return (
    <dialog
      ref={dialog}
      className="about-dialog validation-dialog"
      aria-labelledby="validation-title"
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
          <h2 id="validation-title">
            <BarChart3 size={20} /> {t('validation.open')}
          </h2>
          <button className="icon-button" aria-label={t('validation.close')} onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <p className="about-lead">{t('validation.lead')}</p>

        <section aria-labelledby="validation-mri">
          <h3 id="validation-mri">{t('validation.mriHeading')}</h3>
          <p>{t('validation.mriBody')}</p>
          <MetricTable label={t('validation.mriHeading')} rows={diceRows} t={t} format={format} />
        </section>

        <section aria-labelledby="validation-pathology">
          <h3 id="validation-pathology">{t('validation.pathologyHeading')}</h3>
          <p>{t('validation.pathologyBody')}</p>
          <MetricTable
            label={t('validation.pathologyHeading')}
            rows={pathologyRows}
            t={t}
            format={format}
          />
          <h4>{t('validation.perClassHeading')}</h4>
          <p>{t('validation.perClassBody')}</p>
          <PerClassTable rows={pathology.perClass} t={t} format={format} />
          {/* Esik bir ayar degil, olculmus bir davranistir: kapsam, iki
              doguluk ve yakalanan hata payi birlikte yaziliyor. */}
          <h4>{t('validation.abstentionHeading')}</h4>
          <p>
            {t('validation.abstentionBody', {
              threshold: format.score(pathology.abstention.threshold, 2),
              coverage: format.percent(pathology.abstention.coverage),
              kept: format.score(pathology.abstention.accuracyKept),
              abstained: format.score(pathology.abstention.accuracyAbstained),
            })}
          </p>
          <p className="about-note">
            {t('validation.abstentionLimit', {
              caught: format.count(pathology.abstention.errorsCaught),
              total: format.count(pathology.abstention.errorsTotal),
            })}
          </p>
        </section>

        {/* Uyarilar sayilarla ayni ekranda durur: ayri bir sayfaya tasinirsa
            sayilar uyarisiz okunur. */}
        <section aria-labelledby="validation-warnings">
          <h3 id="validation-warnings">{t('validation.warningsHeading')}</h3>
          <ul className="about-list">
            <li>{t('validation.warningVal')}</li>
            <li>{t('validation.warningDice')}</li>
            <li>{t('validation.warningSmoke')}</li>
          </ul>
        </section>

        <section aria-labelledby="validation-figures">
          <h3 id="validation-figures">{t('validation.figuresHeading')}</h3>
          <p>{t('validation.figuresBody')}</p>
          {figures.isPending ? (
            <p role="status">
              <RefreshCw size={14} className="spin" /> {t('workspace.waiting')}
            </p>
          ) : figures.isError ? (
            <p role="alert">{t('validation.figuresFailed')}</p>
          ) : figures.data.length === 0 ? (
            <p>{t('validation.figuresEmpty')}</p>
          ) : (
            figures.data.map((figure) => (
              <Figure key={figure.id} figure={figure} t={t} format={format} />
            ))
          )}
        </section>
        <p className="about-note">{t('validation.sourceNote')}</p>
      </div>
    </dialog>
  );
}
