import { AlertTriangle } from 'lucide-react';
import type { ReviewFlag } from '../data/contracts';
import type { MessageKey } from '../i18n/messages';
import { useT } from '../i18n';
import { useFormat } from '../format';

// `review_flags()` bulguyu, gerekcesini ve sayilarini birlikte veriyor. Ekran
// gerekceyi kendi dilinde yaziyor; tanimadigi bir gerekce gelirse bayragi
// yutmuyor, manifestin kendi metnini gosteriyor.
const reasonKeys: Record<string, MessageKey> = {
  non_enhancing_tumor: 'flag.reasonNonEnhancing',
};
const evidenceKeys: Record<string, MessageKey> = {
  tumor_core_voxels: 'flag.evidenceCore',
  enhancing_voxels: 'flag.evidenceEnhancing',
  enhancing_threshold: 'flag.evidenceThreshold',
};

export function ReviewFlagBand({ flags }: { flags: ReviewFlag[] }) {
  const t = useT();
  const format = useFormat();
  if (flags.length === 0) return null;
  return (
    <section className="flag-band" aria-label={t('flag.heading')}>
      <h3>
        <AlertTriangle size={16} /> {t('flag.heading')}
      </h3>
      {flags.map((flag) => (
        <div key={`${flag.finding}:${flag.reason}`} className="flag-item">
          <p>{flag.reason in reasonKeys ? t(reasonKeys[flag.reason]) : flag.message}</p>
          <dl className="flag-evidence">
            {Object.entries(flag.evidence).map(([name, value]) => (
              <div key={name}>
                <dt>{name in evidenceKeys ? t(evidenceKeys[name]) : name}</dt>
                <dd>
                  {format.count(value)}
                  {name in evidenceKeys ? ` ${t('flag.voxels')}` : ''}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </section>
  );
}
