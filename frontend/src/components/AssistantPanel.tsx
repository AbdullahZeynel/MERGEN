import { useEffect, useRef } from 'react';
import { MessageSquare, X, Send, Link2Off } from 'lucide-react';
import { EmptyState } from './EmptyState';

export function AssistantPanel({ caseId, close }: { caseId: string | null; close: () => void }) {
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
    <aside className="assistant panel" aria-label="MERGEN Asistan">
      <div className="panel-heading">
        <span>
          <MessageSquare size={18} /> MERGEN Asistan
        </span>
        <button ref={closeRef} className="icon-button" aria-label="Asistanı kapat" onClick={close}>
          <X size={18} />
        </button>
      </div>
      <div className="assistant-context">
        <span className="eyebrow">VAKA BAĞLAMI</span>
        <strong>{caseId ?? 'Vaka seçilmedi'}</strong>
      </div>
      <EmptyState icon={<MessageSquare size={28} />} title="Birlikte incelemek için">
        Vaka odaklı soru ve yanıtlar bu alanda yer alacak. Asistan servisi henüz bağlı değil.
      </EmptyState>
      <div className="assistant-input">
        <div className="offline-line">
          <Link2Off size={14} /> Bağlantı kurulmadı
        </div>
        <label className="sr-only" htmlFor="message">
          Asistana soru
        </label>
        <textarea id="message" disabled placeholder="Asistan bağlandığında soru sorabilirsiniz…" />
        <button className="send-button" disabled aria-label="Mesaj gönder">
          <Send size={17} />
        </button>
      </div>
    </aside>
  );
}
