import { lazy, Suspense } from 'react';
import { Box } from 'lucide-react';
import { EmptyState } from './EmptyState';
import { useT } from '../i18n';
import type { MessageKey } from '../i18n/messages';

const VolumeViewer = lazy(() =>
  import('./VolumeViewer').then((module) => ({ default: module.VolumeViewer })),
);

export function LazyVolumeViewer({ url, fallbackHint }: { url?: string; fallbackHint?: MessageKey }) {
  const t = useT();
  return (
    <Suspense
      fallback={
        <div className="mesh-stage" aria-busy="true">
          <div className="mesh-message" role="status" aria-live="polite">
            <EmptyState icon={<Box />} title={t('viewer.preparing')}>
              {t('viewer.preparingBody')}
            </EmptyState>
          </div>
        </div>
      }
    >
      <VolumeViewer url={url} fallbackHint={fallbackHint} />
    </Suspense>
  );
}
