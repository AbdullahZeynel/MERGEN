import { useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Expand, Minimize } from 'lucide-react';
import { useT } from '../i18n';

export function ViewerFrame({
  title,
  icon,
  children,
  tour,
}: {
  title: string;
  icon: ReactNode;
  children: ReactNode;
  /** Tanitim turunun bu cerceveyi bulmasi icin `data-tour` degeri. */
  tour?: string;
}) {
  const t = useT();
  const [expanded, setExpanded] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!expanded) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog.current?.showModal();
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        setExpanded(false);
      }
    };
    window.addEventListener('keydown', escape, true);
    return () => {
      window.removeEventListener('keydown', escape, true);
      document.body.style.overflow = overflow;
      queueMicrotask(() => toggle.current?.focus());
    };
  }, [expanded]);
  const content = (
    <section
      className={`panel viewer-frame ${expanded ? 'viewer-expanded' : ''}`}
      data-tour={tour}
      aria-label={title}
    >
      <div className="panel-heading">
        <span>
          {icon}
          {title}
        </span>
        <button
          ref={toggle}
          className="icon-button"
          onClick={() => setExpanded(!expanded)}
          aria-label={`${title} ${expanded ? t('viewer.collapse') : t('viewer.expand')}`}
          aria-expanded={expanded}
        >
          {expanded ? <Minimize size={18} /> : <Expand size={18} />}
        </button>
      </div>
      {children}
    </section>
  );
  return expanded
    ? createPortal(
        <dialog
          ref={dialog}
          className="viewer-dialog"
          aria-label={`${title} ${t('viewer.wideView')}`}
          onCancel={() => setExpanded(false)}
        >
          {content}
        </dialog>,
        document.body,
      )
    : content;
}
