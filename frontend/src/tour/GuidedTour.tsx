import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { useT } from '../i18n';
import { steps, type TourActions, type TourStep } from './steps';

const PAD = 8;
const CARD_W = 340;
const GAP = 14;

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

function measure(step: TourStep): { el: HTMLElement; box: Box } | null {
  const el = document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (!r.width && !r.height) return null;
  // Sayfa boyu uzun bir hedef (vaka listesi) ekrani asmasin: spot gorunur
  // kisma kirpilir, kart da ona gore yerlesir.
  const top = Math.max(r.top, 0);
  const bottom = Math.min(r.bottom, window.innerHeight);
  return { el, box: { top: top - PAD, left: r.left - PAD, width: r.width + PAD * 2, height: Math.max(bottom - top, 0) + PAD * 2 } };
}

/** Karti hedefin yanina koyar; sigmazsa karsi tarafa, sonra ekrana kirpar. */
function place(box: Box, preferred: TourStep['placement'], cardH: number) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const fits = {
    right: box.left + box.width + GAP + CARD_W <= vw,
    left: box.left - GAP - CARD_W >= 0,
    bottom: box.top + box.height + GAP + cardH <= vh,
    top: box.top - GAP - cardH >= 0,
  };
  const order: TourStep['placement'][] = [preferred ?? 'right', 'right', 'bottom', 'left', 'top'];
  const side = order.find((s) => s && fits[s]) ?? 'bottom';
  let top: number;
  let left: number;
  if (side === 'right') {
    top = box.top;
    left = box.left + box.width + GAP;
  } else if (side === 'left') {
    top = box.top;
    left = box.left - GAP - CARD_W;
  } else if (side === 'top') {
    top = box.top - GAP - cardH;
    left = box.left;
  } else {
    top = box.top + box.height + GAP;
    left = box.left;
  }
  top = Math.max(12, Math.min(top, vh - cardH - 12));
  left = Math.max(12, Math.min(left, vw - CARD_W - 12));
  return { top, left, side };
}

export function GuidedTour({ actions, onClose }: { actions: TourActions; onClose: () => void }) {
  const t = useT();
  const [index, setIndex] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number; side: string }>({ top: 12, left: 12, side: 'bottom' });
  const card = useRef<HTMLDivElement>(null);
  const actionsRef = useRef(actions);
  actionsRef.current = actions;

  // Hedefi sahnede olmayan adimlar (ornegin vaka yokken 3D) atlanir.
  const available = steps.filter((s) => document.querySelector(`[data-tour="${s.target}"]`));
  const step = available[index];
  const count = available.length;

  const remeasure = useCallback(() => {
    if (!step) return;
    const found = measure(step);
    if (!found) return;
    setBox(found.box);
    const cardH = card.current?.offsetHeight ?? 180;
    setPos(place(found.box, step.placement, cardH));
  }, [step]);

  useLayoutEffect(() => {
    if (!step) return;
    step.enter?.(actionsRef.current);
    const found = measure(step);
    // Yalnizca gorunmuyorsa kaydir; ortalamak uzun hedeflerde basligi kacirir.
    found?.el.scrollIntoView?.({ block: 'nearest', inline: 'nearest', behavior: 'instant' as ScrollBehavior });
    // Kenar cubugu acilmasi gibi yerlesim degisikliklerinden sonra olc.
    const frame = requestAnimationFrame(() => {
      remeasure();
      card.current?.focus();
    });
    return () => {
      cancelAnimationFrame(frame);
      step.leave?.(actionsRef.current);
    };
  }, [step, remeasure]);

  useEffect(() => {
    window.addEventListener('resize', remeasure);
    window.addEventListener('scroll', remeasure, true);
    return () => {
      window.removeEventListener('resize', remeasure);
      window.removeEventListener('scroll', remeasure, true);
    };
  }, [remeasure]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key === 'ArrowRight' && index < count - 1) setIndex(index + 1);
      else if (e.key === 'ArrowLeft' && index > 0) setIndex(index - 1);
    };
    window.addEventListener('keydown', key, true);
    return () => window.removeEventListener('keydown', key, true);
  }, [index, count, onClose]);

  if (!step) return null;
  const last = index === count - 1;
  return (
    <div className="tour" data-testid="tour">
      {box && (
        <div
          className="tour-spotlight"
          style={{ top: box.top, left: box.left, width: box.width, height: box.height }}
          aria-hidden="true"
        />
      )}
      <div
        ref={card}
        className={`tour-card side-${pos.side}`}
        style={{ top: pos.top, left: pos.left, width: CARD_W }}
        role="dialog"
        aria-labelledby="tour-title"
        tabIndex={-1}
      >
        <button className="icon-button tour-close" aria-label={t('tour.close')} onClick={onClose}>
          <X size={16} />
        </button>
        <span className="tour-progress">{t('guide.step', { index: index + 1, count })}</span>
        <h2 id="tour-title">{t(step.title)}</h2>
        <p>{t(step.body)}</p>
        <div className="tour-dots" aria-hidden="true">
          {available.map((s, i) => (
            <i key={s.id} className={i === index ? 'on' : ''} />
          ))}
        </div>
        <div className="tour-actions">
          <button className="button ghost" disabled={index === 0} onClick={() => setIndex(index - 1)}>
            {t('guide.back')}
          </button>
          {last ? (
            <button className="button primary" onClick={onClose}>
              {t('guide.finish')}
            </button>
          ) : (
            <button className="button primary" onClick={() => setIndex(index + 1)}>
              {t('guide.next')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
