import { useEffect, useRef, useState } from 'react';
import { Compass, LayoutGrid, ScanLine, Box, ShieldCheck, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { useT } from '../i18n';
import type { MessageKey } from '../i18n/messages';

const STORAGE_KEY = 'mergen-guide';

const steps: { icon: ReactNode; title: MessageKey; body: MessageKey }[] = [
  { icon: <LayoutGrid size={22} />, title: 'guide.cases.title', body: 'guide.cases.body' },
  { icon: <ScanLine size={22} />, title: 'guide.slices.title', body: 'guide.slices.body' },
  { icon: <Box size={22} />, title: 'guide.mesh.title', body: 'guide.mesh.body' },
  { icon: <ShieldCheck size={22} />, title: 'guide.limits.title', body: 'guide.limits.body' },
];

/** Ilk ziyarette sorar. "Hayir" da bir cevaptir: bir daha sormaz. */
export function shouldAskForGuide(): boolean {
  try {
    return window.localStorage?.getItem(STORAGE_KEY) === null;
  } catch {
    return false; // Depolama kapali bir tarayicida her acilista sormaktansa hic sorma.
  }
}

function remember() {
  try {
    window.localStorage?.setItem(STORAGE_KEY, 'answered');
  } catch {
    /* Depolama yoksa tanitim yine calisir, yalnizca hatirlanmaz. */
  }
}

export function WelcomeGuide({
  mode,
  onClose,
}: {
  // 'ask' ilk ziyaret, 'tour' alt bilgiden acilan tekrar.
  mode: 'ask' | 'tour';
  onClose: () => void;
}) {
  const t = useT();
  const [step, setStep] = useState(mode === 'tour' ? 0 : -1);
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
  const finish = () => {
    remember();
    onClose();
  };
  const asking = step < 0;
  const current = steps[Math.max(step, 0)];
  return (
    <dialog
      ref={dialog}
      className="guide-dialog"
      aria-labelledby="guide-title"
      onCancel={(event) => {
        event.preventDefault();
        finish();
      }}
    >
      <div className="guide-body">
        <button className="icon-button guide-dismiss" aria-label={t('guide.close')} onClick={finish}>
          <X size={18} />
        </button>
        {asking ? (
          <>
            <div className="guide-icon" aria-hidden="true">
              <Compass size={22} />
            </div>
            <h2 id="guide-title">{t('guide.askTitle')}</h2>
            <p>{t('guide.askBody')}</p>
            <div className="guide-actions">
              <button className="button ghost" onClick={finish}>
                {t('guide.decline')}
              </button>
              <button className="button primary" onClick={() => setStep(0)}>
                {t('guide.accept')}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="guide-icon" aria-hidden="true">
              {current.icon}
            </div>
            <span className="guide-progress">
              {t('guide.step', { index: step + 1, count: steps.length })}
            </span>
            <h2 id="guide-title">{t(current.title)}</h2>
            <p>{t(current.body)}</p>
            <div className="guide-dots" aria-hidden="true">
              {steps.map((item, index) => (
                <i key={item.title} className={index === step ? 'on' : ''} />
              ))}
            </div>
            <div className="guide-actions">
              <button
                className="button ghost"
                disabled={step === 0}
                onClick={() => setStep(step - 1)}
              >
                {t('guide.back')}
              </button>
              {step === steps.length - 1 ? (
                <button className="button primary" onClick={finish}>
                  {t('guide.finish')}
                </button>
              ) : (
                <button className="button primary" onClick={() => setStep(step + 1)}>
                  {t('guide.next')}
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </dialog>
  );
}
