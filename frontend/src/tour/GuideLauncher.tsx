import { Compass } from 'lucide-react';
import { useT } from '../i18n';

const STORAGE_KEY = 'mergen-guide';

/** Ilk ziyarette baloncuk gosterilir mi; "hayir" da bir cevaptir. */
export function shouldNudge(): boolean {
  try {
    return window.localStorage?.getItem(STORAGE_KEY) === null;
  } catch {
    return false;
  }
}

export function rememberAnswered() {
  try {
    window.localStorage?.setItem(STORAGE_KEY, 'answered');
  } catch {
    /* depolama yoksa yalnizca hatirlanmaz */
  }
}

/** Raydaki rehber dugmesi ve ilk ziyarette ustunde beliren davet. */
export function GuideLauncher({
  nudge,
  onStart,
  onDismiss,
}: {
  nudge: boolean;
  onStart: () => void;
  onDismiss: () => void;
}) {
  const t = useT();
  return (
    <div className="guide-launcher">
      <button className="rail-button" aria-label={t('tour.open')} onClick={onStart}>
        <Compass size={21} />
      </button>
      {nudge && (
        <div className="guide-nudge" role="status">
          <strong>{t('guide.askTitle')}</strong>
          <span>{t('tour.nudgeBody')}</span>
          <div className="guide-nudge-actions">
            <button className="link-button" onClick={onDismiss}>
              {t('tour.notNow')}
            </button>
            <button className="button primary small" onClick={onStart}>
              {t('tour.start')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
