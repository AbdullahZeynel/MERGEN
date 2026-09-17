import { useCallback, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  ChevronRight,
  Database,
  FolderOpen,
  Languages,
  LayoutGrid,
  Link2Off,
  Menu,
  MessageSquare,
  Moon,
  RefreshCw,
  Search,
  ShieldCheck,
  Sun,
  X,
} from 'lucide-react';
import { demoSource, liveSource } from './data/source';
import { statusKeys, type SourceMode, type CaseRecord } from './data/contracts';
import { useLanguage } from './i18n';
import { EmptyState } from './components/EmptyState';
import { ImagingWorkspace } from './components/ImagingWorkspace';
import { AssistantPanel } from './components/AssistantPanel';
import { AboutDialog } from './components/AboutDialog';
import { GuidedTour } from './tour/GuidedTour';
import { GuideLauncher, rememberAnswered, shouldNudge } from './tour/GuideLauncher';
import { TOUR_SPIN_EVENT } from './tour/steps';

// Deferred until chatbot integration; keep the component for the next sprint.
const assistantEnabled = false;
// styles.css icindeki dar ekran kirilma noktasiyla ayni deger.
const DAR_EKRAN = 760;
type Theme = 'light' | 'dark';

function initialTheme(): Theme {
  const saved = window.localStorage.getItem('mergen-theme');
  if (saved === 'light' || saved === 'dark') return saved;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export default function App() {
  const { language, setLanguage, t } = useLanguage();
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [mode, setMode] = useState<SourceMode>('demo');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [assistantOpen, setAssistantOpen] = useState(false);
  // Vaka listesi genis ekranda acik, dar ekranda kapali baslar. Raydaki dugme
  // her iki genislikte de ayni durumu cevirir.
  const [casesOpen, setCasesOpen] = useState(() => window.innerWidth > DAR_EKRAN);
  const [aboutOpen, setAboutOpen] = useState(false);
  // Tur raydaki dugmeden her zaman acilir; ilk ziyarette dugmenin ustunde bir
  // davet belirir ve verilen cevap (evet ya da simdi degil) hatirlanir.
  const [tourOpen, setTourOpen] = useState(false);
  const [nudge, setNudge] = useState(shouldNudge);
  const startTour = useCallback(() => {
    rememberAnswered();
    setNudge(false);
    setTourOpen(true);
  }, []);
  const dismissNudge = useCallback(() => {
    rememberAnswered();
    setNudge(false);
  }, []);
  const tourActions = {
    openCases: () => setCasesOpen(true),
    spin3d: (on: boolean) =>
      window.dispatchEvent(new CustomEvent(TOUR_SPIN_EVENT, { detail: { on } })),
  };
  const closeAssistant = useCallback(() => setAssistantOpen(false), []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem('mergen-theme', theme);
  }, [theme]);
  const query = useQuery({
    queryKey: ['cases', mode],
    queryFn: ({ signal }) => (mode === 'demo' ? demoSource : liveSource).listCases(signal),
  });
  const cases = query.data ?? [];
  const filtered = cases.filter(
    (c) =>
      c.id.toLowerCase().includes(search.toLowerCase().trim()) &&
      (filter === 'all' || c.status === filter),
  );
  const record = filtered.find((c) => c.id === selectedId) ?? filtered[0] ?? null;
  const imagingIndex = record
    ? cases.findIndex((candidate) => candidate.id === record.id)
    : -1;
  const nextMeshUrl = imagingIndex >= 0
    ? cases.slice(imagingIndex + 1).find((candidate) => candidate.mesh)?.mesh
    : undefined;
  const changeMode = (value: SourceMode) => {
    setMode(value);
    setSelectedId(null);
    setSearch('');
    setFilter('all');
  };

  return (
    <div className="app">
      <a className="skip-link" href="#workspace">
        {t('app.skip')}
      </a>
      <nav className="rail" aria-label={t('app.nav')}>
        <a href="#workspace" className="brand-mark" aria-label={t('app.brand')}>
          <img src="/ergenekon-logo.png" alt="" width={192} height={88} />
        </a>
        <button
          className={`rail-button ${casesOpen ? 'active' : ''}`}
          data-tour="cases-toggle"
          aria-label={casesOpen ? t('cases.hide') : t('cases.show')}
          aria-expanded={casesOpen}
          aria-controls="case-sidebar"
          onClick={() => setCasesOpen(!casesOpen)}
        >
          <LayoutGrid size={21} />
        </button>
        {assistantEnabled && (
          <button
            className={`rail-button ${assistantOpen ? 'active' : ''}`}
            aria-label={t('assistant.open')}
            aria-expanded={assistantOpen}
            onClick={() => setAssistantOpen(!assistantOpen)}
          >
            <MessageSquare size={21} />
          </button>
        )}
        <GuideLauncher nudge={nudge} onStart={startTour} onDismiss={dismissNudge} />
      </nav>
      <div className="app-body">
        <header className="topbar">
          <div className="wordmark">
            MERGEN<span>{t('app.wordmarkSub')}</span>
          </div>
          <div className="topbar-right">
            <button
              className="theme-toggle source-toggle"
              type="button"
              data-tour="data-sources"
              onClick={() => setAboutOpen(true)}
            >
              <ShieldCheck size={16} />
              <span>{t('about.open')}</span>
            </button>
            <button
              className="theme-toggle"
              type="button"
              aria-label={theme === 'dark' ? t('theme.toLight') : t('theme.toDark')}
              aria-pressed={theme === 'dark'}
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            >
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
              <span>{theme === 'dark' ? t('theme.light') : t('theme.dark')}</span>
            </button>
            <button
              className="theme-toggle language-toggle"
              type="button"
              aria-label={t('language.switch')}
              onClick={() => setLanguage(language === 'tr' ? 'en' : 'tr')}
            >
              <Languages size={16} />
              <span>{t('language.short')}</span>
            </button>
          </div>
        </header>
        <div className="app-content">
          <aside
            id="case-sidebar"
            className={`case-sidebar ${casesOpen ? 'open' : 'collapsed'}`}
            aria-label={t('cases.title')}
          >
            <div className="sidebar-title">
              <h1>
                {t('cases.title')} <span>{cases.length.toString().padStart(2, '0')}</span>
              </h1>
              <button
                className="icon-button mobile-only"
                aria-label={t('cases.close')}
                onClick={() => setCasesOpen(false)}
              >
                <X />
              </button>
            </div>
            <p className="sidebar-description">{t('cases.pick')}</p>
            <div className="source-switch segmented" data-tour="source-switch" aria-label={t('cases.sourceLabel')}>
              <button
                className={mode === 'demo' ? 'selected' : ''}
                aria-pressed={mode === 'demo'}
                onClick={() => changeMode('demo')}
              >
                {t('cases.demo')}
              </button>
              <button
                className={mode === 'live' ? 'selected' : ''}
                aria-pressed={mode === 'live'}
                onClick={() => changeMode('live')}
              >
                {t('cases.live')}
              </button>
            </div>
            <label className="search-box">
              <Search size={17} />
              <span className="sr-only">{t('cases.search')}</span>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('cases.searchPlaceholder')}
              />
            </label>
            <div className="list-label">
              <span>{t('cases.listLabel')}</span>
              <select
                aria-label={t('cases.filter')}
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              >
                <option value="all">{t('cases.allStatuses')}</option>
                {Object.entries(statusKeys).map(([status, key]) => (
                  <option key={status} value={status}>
                    {t(key)}
                  </option>
                ))}
              </select>
            </div>
            <div className="case-list" data-tour="case-list" aria-busy={query.isPending}>
              {query.isPending ? (
                <p role="status" className="list-message">
                  {t('cases.loading')}
                </p>
              ) : (
                filtered.map((c) => (
                  <button
                    key={c.id}
                    className={`case-item ${record?.id === c.id ? 'selected' : ''}`}
                    aria-pressed={record?.id === c.id}
                    onClick={() => {
                      setSelectedId(c.id);
                      // Dar ekranda liste calisma alaninin ustune biniyor;
                      // secimden sonra kapaniyor. Genis ekranda acik kaliyor.
                      if (window.innerWidth <= DAR_EKRAN) setCasesOpen(false);
                    }}
                  >
                    <span className="case-icon">
                      <FolderOpen size={20} />
                    </span>
                    <span className="case-item-text">
                      <strong>{c.id}</strong>
                      <span>{t('cases.modality')}</span>
                      <span className="status-pill">
                        <span />
                        {t(statusKeys[c.status])}
                      </span>
                    </span>
                    <ChevronRight size={15} />
                  </button>
                ))
              )}
              {!query.isPending && filtered.length === 0 && (
                <p className="list-message">
                  {query.isError ? t('cases.listFailed') : t('cases.noMatch')}
                </p>
              )}
            </div>
          </aside>
          <main id="workspace" className="workspace" tabIndex={-1}>
            <div className="breadcrumb">
              <button
                className="icon-button mobile-only"
                aria-label={t('workspace.showCases')}
                onClick={() => setCasesOpen(true)}
              >
                <Menu size={18} />
              </button>
              <span>{t('workspace.breadcrumb')}</span>
              <ChevronRight size={14} />
              <strong>{record?.id ?? t(mode === 'demo' ? 'cases.demo' : 'cases.live')}</strong>
            </div>
            <div className="workspace-title">
              <div>
                <span className="eyebrow">{t('workspace.eyebrow')}</span>
                <h2>{record?.id ?? t('workspace.emptyTitle')}</h2>
                {!record && <p>{t('workspace.emptyBody')}</p>}
              </div>
              {assistantEnabled && (
                <button
                  className="button assistant-toggle"
                  onClick={() => setAssistantOpen(!assistantOpen)}
                  aria-expanded={assistantOpen}
                >
                  <MessageSquare size={17} /> Asistan <ArrowRight size={16} />
                </button>
              )}
            </div>
            <div className="context-bar" data-tour="context-bar">
              <span className={`mode-badge ${mode}`}>
                <Database size={14} />
                {t(mode === 'demo' ? 'workspace.modeDemo' : 'workspace.modeLive')}
              </span>
              {/* Yalnizca vaka listesi isteginin sonucu; kesit/mesh
                  istekleri ayrica hata verebilir, o yuzden metin liste diyor. */}
              <span className="service-state" role="status">
                {query.isPending ? (
                  <><RefreshCw size={14} className="spin" /> {t('workspace.waiting')}</>
                ) : query.isError ? (
                  <>
                    <Link2Off size={14} />{' '}
                    {t(mode === 'demo' ? 'workspace.demoUnreachable' : 'workspace.liveDisconnected')}
                  </>
                ) : (
                  <>
                    <Database size={14} />{' '}
                    {t(mode === 'demo' ? 'workspace.demoListed' : 'workspace.liveListed')}
                  </>
                )}
              </span>
              <button
                className="refresh"
                aria-label={t('workspace.refresh')}
                disabled={query.isFetching}
                onClick={() => void query.refetch()}
              >
                <RefreshCw size={16} className={query.isFetching ? 'spin' : ''} />
              </button>
            </div>
            <div className="content-with-assistant">
              <div className="analysis-content">
                {query.isPending ? (
                  <div className="panel loading-panel" role="status">
                    <RefreshCw className="spin" /> {t('workspace.loadingCase')}
                  </div>
                ) : query.isError ? (
                  <div className="panel" role="alert">
                    <EmptyState
                      icon={<Link2Off />}
                      title={
                        t(mode === 'live' ? 'workspace.liveNotReadyTitle' : 'workspace.demoUnreadableTitle')
                      }
                      action={
                        <button
                          className="button"
                          onClick={() =>
                            mode === 'live' ? changeMode('demo') : void query.refetch()
                          }
                        >
                          {t(mode === 'live' ? 'workspace.backToDemo' : 'workspace.retry')}
                        </button>
                      }
                    >
                      {t(mode === 'live' ? 'workspace.liveNeedsServices' : 'workspace.demoMissing')}
                    </EmptyState>
                  </div>
                ) : !record ? (
                  <div className="panel">
                    <EmptyState icon={<FolderOpen />} title={t('workspace.noCaseTitle')}>
                      {t('workspace.noCaseBody')}
                    </EmptyState>
                  </div>
                ) : (
                  <ImagingWorkspace
                    key={`${mode}:${record.id}`}
                    record={record as CaseRecord}
                    nextMeshUrl={nextMeshUrl}
                  />
                )}
              </div>
              {assistantEnabled && assistantOpen && (
                <AssistantPanel
                  key={record?.id ?? mode}
                  caseId={record?.id ?? null}
                  close={closeAssistant}
                />
              )}
            </div>
            <footer className="workspace-footer">
              <span>
                MERGEN <span className="muted">/</span> ERGENEKON
              </span>
              <span>{t('footer.purpose')}</span>
              <span className="footer-links">
                <button className="link-button" onClick={() => setAboutOpen(true)}>
                  {t('about.open')}
                </button>
                <button className="link-button" onClick={startTour}>
                  {t('guide.reopen')}
                </button>
              </span>
            </footer>
          </main>
        </div>
      </div>
      {aboutOpen && <AboutDialog onClose={() => setAboutOpen(false)} />}
      {tourOpen && <GuidedTour actions={tourActions} onClose={() => setTourOpen(false)} />}
    </div>
  );
}
