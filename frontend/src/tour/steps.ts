import type { MessageKey } from '../i18n/messages';

/** Turun sahnede dokundugu hooklar; App bunlari gercek duruma baglar. */
export interface TourActions {
  openCases: () => void;
  spin3d: (on: boolean) => void;
}

export interface TourStep {
  id: string;
  /** `data-tour` degeri; sahnede bulunamazsa adim atlanir. */
  target: string;
  title: MessageKey;
  body: MessageKey;
  /** Adima girerken calisir (kenar cubugunu acmak, modeli dondurmek). */
  enter?: (actions: TourActions) => void;
  leave?: (actions: TourActions) => void;
  /** Kartin hedefe gore tercih edilen yeri. */
  placement?: 'right' | 'bottom' | 'left' | 'top';
}

export const TOUR_SPIN_EVENT = 'mergen:tour-spin';

export const steps: TourStep[] = [
  {
    id: 'cases',
    target: 'case-list',
    title: 'tour.cases.title',
    body: 'tour.cases.body',
    enter: (a) => a.openCases(),
    placement: 'right',
  },
  {
    id: 'module',
    target: 'module-switch',
    title: 'tour.module.title',
    body: 'tour.module.body',
    enter: (a) => a.openCases(),
    placement: 'right',
  },
  {
    id: 'source',
    target: 'source-switch',
    title: 'tour.source.title',
    body: 'tour.source.body',
    placement: 'right',
  },
  {
    id: 'context',
    target: 'context-bar',
    title: 'tour.context.title',
    body: 'tour.context.body',
    placement: 'bottom',
  },
  {
    id: 'slices',
    target: 'slice-viewer',
    title: 'tour.slices.title',
    body: 'tour.slices.body',
    placement: 'right',
  },
  {
    id: 'layers',
    target: 'overlay-controls',
    title: 'tour.layers.title',
    body: 'tour.layers.body',
    placement: 'top',
  },
  {
    id: 'mesh',
    target: 'mesh-viewer',
    title: 'tour.mesh.title',
    body: 'tour.mesh.body',
    enter: (a) => a.spin3d(true),
    leave: (a) => a.spin3d(false),
    placement: 'left',
  },
  {
    id: 'regions',
    target: 'region-controls',
    title: 'tour.regions.title',
    body: 'tour.regions.body',
    placement: 'top',
  },
  {
    id: 'slide',
    target: 'slide-prediction',
    title: 'tour.slide.title',
    body: 'tour.slide.body',
    placement: 'top',
  },
  {
    id: 'validation',
    target: 'validation',
    title: 'tour.validation.title',
    body: 'tour.validation.body',
    placement: 'bottom',
  },
  {
    id: 'sources',
    target: 'data-sources',
    title: 'tour.sources.title',
    body: 'tour.sources.body',
    placement: 'bottom',
  },
];
