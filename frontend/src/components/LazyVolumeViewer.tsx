import { lazy, Suspense } from 'react';
import { Box } from 'lucide-react';
import { EmptyState } from './EmptyState';

const VolumeViewer = lazy(() =>
  import('./VolumeViewer').then((module) => ({ default: module.VolumeViewer })),
);

export function LazyVolumeViewer({ url }: { url?: string }) {
  return (
    <Suspense
      fallback={
        <div className="mesh-stage" aria-busy="true">
          <div className="mesh-message" role="status" aria-live="polite">
            <EmptyState icon={<Box />} title="3D görüntüleyici hazırlanıyor…">
              Etkileşimli görüntüleyici kodu yükleniyor.
            </EmptyState>
          </div>
        </div>
      }
    >
      <VolumeViewer url={url} />
    </Suspense>
  );
}
