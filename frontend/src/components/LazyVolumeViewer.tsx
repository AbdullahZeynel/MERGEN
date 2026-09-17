import { lazy, Suspense } from 'react';
import { Box } from 'lucide-react';
import { EmptyState } from './EmptyState';
import { useT } from '../i18n';

const VolumeViewer = lazy(() =>
  import('./VolumeViewer').then((module) => ({ default: module.VolumeViewer })),
);

export function LazyVolumeViewer({ url }: { url?: string }) {
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
      <VolumeViewer url={url} />
    </Suspense>
  );
}
