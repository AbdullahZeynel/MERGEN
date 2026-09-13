import { useQuery } from '@tanstack/react-query';
import { Dna, Info, TriangleAlert } from 'lucide-react';
import { loadGenomicsReport, type GenomicsCase } from '../data/genomics';
import { EmptyState } from './EmptyState';

const yuzde = (deger: number) => `%${(deger * 100).toFixed(2)}`;
const isaretli = (deger: number) => `${deger >= 0 ? '+' : '−'}${Math.abs(deger).toFixed(3)}`;

export function GenomicsWorkspace({ record }: { record: GenomicsCase }) {
  const query = useQuery({
    queryKey: ['genomics-report', record.id],
    queryFn: ({ signal }) => loadGenomicsReport(record, signal),
  });

  if (query.isPending)
    return (
      <section className="panel genomics-panel">
        <p role="status" className="list-message">
          Genomik sonuç yükleniyor…
        </p>
      </section>
    );

  if (query.isError || !query.data)
    return (
      <section className="panel genomics-panel">
        <EmptyState icon={<TriangleAlert size={34} />} title="Genomik sonuç okunamadı">
          {query.error instanceof Error
            ? query.error.message
            : 'Demo paketi hazırlanmamış olabilir.'}
        </EmptyState>
      </section>
    );

  const { result, explanation } = query.data;
  const { prediction } = result;
  // En büyük mutlak katkıya göre çubuk genişliği; işaret yönü korunur.
  const enBuyuk = Math.max(
    ...explanation.topFeatures.map((f) => Math.abs(f.contribution)),
    1e-9,
  );

  return (
    <section className="panel genomics-panel">
      <div className="panel-heading">
        <span>
          <Dna size={18} /> Varyant patojenite tahmini
        </span>
        <span className="small muted">
          {result.modelId} · {result.modelVersion}
        </span>
      </div>

      <dl className="genomics-summary">
        <div>
          <dt>Varyant</dt>
          <dd>
            <strong>{result.variant.gene}</strong> {result.variant.proteinChange}
          </dd>
        </div>
        <div>
          <dt>Patojenite olasılığı</dt>
          <dd className="genomics-score">{yuzde(prediction.pathogenicityProbability)}</dd>
        </div>
        <div>
          <dt>Karar</dt>
          <dd>
            <span className={`genomics-class ${prediction.class}`}>
              {prediction.class === 'pathogenic' ? 'Patojenik' : 'Benign'}
            </span>
            <span className="small muted"> · eşik {prediction.decisionThreshold}</span>
          </dd>
        </div>
        <div>
          <dt>ESM-2 LLR</dt>
          <dd>{result.features.esm_llr?.toFixed(4) ?? '—'}</dd>
        </div>
      </dl>

      <div className="genomics-shap">
        <div className="panel-heading">
          <span>En etkili özellikler</span>
          {/* Katkilarin hangi uzayda oldugu ve toplami tek satirda. */}
          <span className="small muted">
            log-odds · taban {explanation.baseValue.toFixed(3)} · margin{' '}
            {explanation.rawMargin.toFixed(3)}
          </span>
        </div>
        <ul>
          {explanation.topFeatures.map((f) => (
            <li key={f.feature}>
              <span className="shap-name">{f.feature}</span>
              <span className="shap-bar" aria-hidden="true">
                <i
                  className={f.contribution >= 0 ? 'positive' : 'negative'}
                  style={{ width: `${(Math.abs(f.contribution) / enBuyuk) * 100}%` }}
                />
              </span>
              <span className="shap-value">{isaretli(f.contribution)}</span>
            </li>
          ))}
        </ul>
      </div>

      {result.notes.length > 0 && (
        <ul className="genomics-notes">
          {result.notes.map((n) => (
            <li key={n}>
              <Info size={15} /> <span>{n}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="notice">
        <Info size={16} />
        <span>
          Kamuya açık referans varyanttır; görüntü vakasıyla eşleştirilmemiştir ve
          klinik karar için kullanılamaz.
        </span>
      </div>
    </section>
  );
}
