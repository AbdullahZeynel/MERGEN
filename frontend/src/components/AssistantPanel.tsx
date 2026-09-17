import { useEffect, useRef } from 'react';
import { MessageSquare, X, Send, Link2Off } from 'lucide-react';
import { EmptyState } from './EmptyState';
import { useT } from '../i18n';

export function AssistantPanel({ caseId, close }: { caseId: string | null; close: () => void }) {
  const t = useT();
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('keydown', escape);
      previous?.focus();
    };
  }, [close]);
  return (
    <aside className="assistant panel" aria-label={t('assistant.name')}>
      <div className="panel-heading">
        <span>
          <MessageSquare size={18} /> {t('assistant.name')}
        </span>
        <button ref={closeRef} className="icon-button" aria-label={t('assistant.close')} onClick={close}>
          <X size={18} />
        </button>
      </div>
      <div className="assistant-context">
        <span className="eyebrow">{t('assistant.contextEyebrow')}</span>
        <strong>{caseId ?? t('assistant.noCase')}</strong>
      </div>
      <EmptyState icon={<MessageSquare size={28} />} title={t('assistant.title')}>
        {t('assistant.body')}
      </EmptyState>
      <div className="assistant-input">
        <div className="offline-line">
          <Link2Off size={14} /> {t('assistant.offline')}
        </div>
        <label className="sr-only" htmlFor="message">
          {t('assistant.inputLabel')}
        </label>
        <textarea id="message" disabled placeholder={t('assistant.placeholder')} />
        <button className="send-button" disabled aria-label={t('assistant.send')}>
          <Send size={17} />
        </button>
      </div>
    </aside>
  );
}
