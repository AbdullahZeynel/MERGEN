import { useCallback, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  ChevronRight,
  Database,
  Dna,
  FolderOpen,
  Info,
  LayoutGrid,
  Link2Off,
  Menu,
  MessageSquare,
  Moon,
  RefreshCw,
  Search,
  Sun,
  ScanLine,
  X,
} from 'lucide-react';
import { listGenomicsCases, type GenomicsCase } from './data/genomics';
import { demoSource, liveSource } from './data/source';
import { statusLabels, type SourceMode, type CaseRecord } from './data/contracts';
import { EmptyState } from './components/EmptyState';
import { GenomicsWorkspace } from './components/GenomicsWorkspace';
import { ImagingWorkspace } from './components/ImagingWorkspace';
import { AssistantPanel } from './components/AssistantPanel';

// Deferred until chatbot integration; keep the component for the next sprint.
const assistantEnabled = false;
type Theme = 'light' | 'dark';

function initialTheme(): Theme {
  const saved = window.localStorage.getItem('mergen-theme');
  if (saved === 'light' || saved === 'dark') return saved;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [mode, setMode] = useState<SourceMode>('demo');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [view, setView] = useState<'imaging' | 'genomics'>('imaging');
  // Modül, vaka listesinin kaynağını değiştirir. Görüntü ve genomik kayıtlar
  // bağımsızdır; modül değişiminde seçim ve arama sıfırlanır.
  const [module, setModule] = useState<'imaging' | 'genomics'>('imaging');
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [mobileCases, setMobileCases] = useState(false);
  const closeAssistant = useCallback(() => setAssistantOpen(false), []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem('mergen-theme', theme);
  }, [theme]);
  const imagingQuery = useQuery({
    queryKey: ['cases', mode],
    queryFn: ({ signal }) => (mode === 'demo' ? demoSource : liveSource).listCases(signal),
    enabled: module === 'imaging',
  });
  const genomicsQuery = useQuery({
    queryKey: ['genomics-cases', mode],
    queryFn: ({ signal }) => listGenomicsCases(signal),
    enabled: module === 'genomics' && mode === 'demo',
  });
  const query = module === 'imaging' ? imagingQuery : genomicsQuery;
  const cases = query.data ?? [];
  const filtered = cases.filter(
    (c) =>
      c.id.toLowerCase().includes(search.toLowerCase().trim()) &&
      (filter === 'all' || c.status === filter),
  );
  const record = filtered.find((c) => c.id === selectedId) ?? filtered[0] ?? null;
  const genomicsRecord = module === 'genomics' ? (record as GenomicsCase | null) : null;
  const changeMode = (value: SourceMode) => {
    setMode(value);
    setSelectedId(null);
    setSearch('');
    setFilter('all');
    setView('imaging');
  };
  const changeModule = (value: 'imaging' | 'genomics') => {
    setModule(value);
    setSelectedId(null);
    setSearch('');
    setFilter('all');
    setView(value === 'genomics' ? 'genomics' : 'imaging');
  };

  return (
    <div className="app">
      <a className="skip-link" href="#workspace">
        Çalışma alanına geç
      </a>
      <nav className="rail" aria-label="Ana gezinme">
        <a href="#workspace" className="brand-mark" aria-label="MERGEN çalışma alanı">
          <img src="/ergenekon-logo.png" alt="" width={192} height={88} />
        </a>
        <button
          className="rail-button active"
          aria-label="Vaka listesi"
          aria-expanded={mobileCases}
          onClick={() => setMobileCases(!mobileCases)}
        >
          <LayoutGrid size={21} />
        </button>
        {assistantEnabled && (
          <button
            className={`rail-button ${assistantOpen ? 'active' : ''}`}
            aria-label="Asistanı aç"
            aria-expanded={assistantOpen}
            onClick={() => setAssistantOpen(!assistantOpen)}
          >
            <MessageSquare size={21} />
          </button>
        )}
      </nav>
      <div className="app-body">
        <header className="topbar">
          <div className="wordmark">
            MERGEN<span>ONKOLOJİ KARAR DESTEĞİ</span>
          </div>
          <div className="topbar-right">
            <button
              className="theme-toggle"
              type="button"
              aria-label={theme === 'dark' ? 'Açık temaya geç' : 'Koyu temaya geç'}
              aria-pressed={theme === 'dark'}
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            >
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
              <span>{theme === 'dark' ? 'Açık' : 'Koyu'}</span>
            </button>
          </div>
        </header>
        <div className="app-content">
          <aside
            className={`case-sidebar ${mobileCases ? 'mobile-open' : ''}`}
            aria-label="Vakalar"
          >
            <div className="sidebar-title">
              <h1>
                Vakalar <span>{cases.length.toString().padStart(2, '0')}</span>
              </h1>
              <button
                className="icon-button mobile-only"
                aria-label="Vaka listesini kapat"
                onClick={() => setMobileCases(false)}
              >
                <X />
              </button>
            </div>
            <p className="sidebar-description">İncelemek için bir vaka seçin.</p>
            <div className="source-switch segmented" aria-label="Veri kaynağı">
              <button
                className={mode === 'demo' ? 'selected' : ''}
                aria-pressed={mode === 'demo'}
                onClick={() => changeMode('demo')}
              >
                Hazır demo
              </button>
              <button
                className={mode === 'live' ? 'selected' : ''}
                aria-pressed={mode === 'live'}
                onClick={() => changeMode('live')}
              >
                Canlı analiz
              </button>
            </div>
            <div className="source-switch segmented" aria-label="Modül">
              <button
                className={module === 'imaging' ? 'selected' : ''}
                aria-pressed={module === 'imaging'}
                onClick={() => changeModule('imaging')}
              >
                Görüntü
              </button>
              <button
                className={module === 'genomics' ? 'selected' : ''}
                aria-pressed={module === 'genomics'}
                onClick={() => changeModule('genomics')}
                disabled={mode !== 'demo'}
              >
                Genomik
              </button>
            </div>
            <label className="search-box">
              <Search size={17} />
              <span className="sr-only">Vaka ara</span>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Vaka kimliği ile ara"
              />
            </label>
            <div className="list-label">
              <span>VAKA LİSTESİ</span>
              <select
                aria-label="Vaka durumunu filtrele"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              >
                <option value="all">Tüm durumlar</option>
                {Object.entries(statusLabels).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="case-list" aria-busy={query.isPending}>
              {query.isPending ? (
                <p role="status" className="list-message">
                  Vakalar yükleniyor…
                </p>
              ) : (
                filtered.map((c) => (
                  <button
                    key={c.id}
                    className={`case-item ${record?.id === c.id ? 'selected' : ''}`}
                    aria-pressed={record?.id === c.id}
                    onClick={() => {
                      setSelectedId(c.id);
                      setMobileCases(false);
                    }}
                  >
                    <span className="case-icon">
                      <FolderOpen size={20} />
                    </span>
                    <span className="case-item-text">
                      <strong>{c.id}</strong>
                      <span>
                        {module === 'genomics'
                          ? `${(c as GenomicsCase).gene} ${(c as GenomicsCase).proteinChange}`
                          : 'MR görüntüleme'}
                      </span>
                      <span className="status-pill">
                        <span />
                        {statusLabels[c.status]}
                      </span>
                    </span>
                    <ChevronRight size={15} />
                  </button>
                ))
              )}
              {!query.isPending && filtered.length === 0 && (
                <p className="list-message">
                  {query.isError ? 'Vaka listesi alınamadı.' : 'Eşleşen vaka bulunamadı.'}
                </p>
              )}
            </div>
          </aside>
          <main id="workspace" className="workspace" tabIndex={-1}>
            <div className="breadcrumb">
              <button
                className="icon-button mobile-only"
                aria-label="Vakaları göster"
                onClick={() => setMobileCases(true)}
              >
                <Menu size={18} />
              </button>
              <span>Çalışma alanı</span>
              <ChevronRight size={14} />
              <strong>{record?.id ?? (mode === 'demo' ? 'Hazır demo' : 'Canlı analiz')}</strong>
            </div>
            <div className="workspace-title">
              <div>
                <span className="eyebrow">VAKA İNCELEME</span>
                <h2>{record?.id ?? 'Vaka çalışma alanı'}</h2>
                <p>
                  {record
                    ? module === 'imaging'
                      ? 'Görüntüler ve analiz sonuçları tek çalışma alanında.'
                      : 'Varyant tahmini ve model açıklaması tek çalışma alanında.'
                    : 'Vaka verileri hazır olduğunda burada görüntülenir.'}
                </p>
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
            <div className="context-bar">
              <span className={`mode-badge ${mode}`}>
                <Database size={14} />
                {mode === 'demo' ? 'HAZIR DEMO' : 'CANLI ANALİZ'}
              </span>
              <span className="context-note">
                {mode === 'demo'
                  ? 'Önceden hazırlanmış vaka verisi'
                  : 'Canlı veri bağlantısı bekleniyor'}
              </span>
              <span className="service-state">
                {mode === 'demo' ? (
                  <><Database size={14} /> VPS demo servisi hazır</>
                ) : (
                  <><Link2Off size={14} /> AI servisi bağlı değil</>
                )}
              </span>
            </div>
            <div className="content-with-assistant">
              <div className="analysis-content">
                <div className="view-tabs" aria-label="Analiz görünümü">
                  {module === 'imaging' && (
                    <>
                      <button
                        aria-pressed={view === 'imaging'}
                        className={view === 'imaging' ? 'selected' : ''}
                        onClick={() => setView('imaging')}
                      >
                        <ScanLine size={18} /> Görüntüleme
                      </button>
                      <button
                        aria-pressed={view === 'genomics'}
                        className={view === 'genomics' ? 'selected' : ''}
                        onClick={() => setView('genomics')}
                      >
                        <Dna size={18} /> Bu vakanın varyantı
                      </button>
                    </>
                  )}
                  {module === 'genomics' && (
                    <span className="view-tabs-label">
                      <Dna size={18} /> Varyant patojenite
                    </span>
                  )}
                  <button
                    className="refresh"
                    aria-label="Vaka verilerini yenile"
                    disabled={query.isFetching}
                    onClick={() => void query.refetch()}
                  >
                    <RefreshCw size={16} className={query.isFetching ? 'spin' : ''} />
                  </button>
                </div>
                {query.isPending ? (
                  <div className="panel loading-panel" role="status">
                    <RefreshCw className="spin" /> Vaka verileri yükleniyor…
                  </div>
                ) : query.isError ? (
                  <div className="panel" role="alert">
                    <EmptyState
                      icon={<Link2Off />}
                      title={
                        mode === 'live' ? 'Canlı bağlantı henüz kurulmadı' : 'Demo paketi okunamadı'
                      }
                      action={
                        <button
                          className="button"
                          onClick={() =>
                            mode === 'live' ? changeMode('demo') : void query.refetch()
                          }
                        >
                          {mode === 'live' ? 'Hazır demolara dön' : 'Yeniden dene'}
                        </button>
                      }
                    >
                      {mode === 'live'
                        ? 'Canlı analiz için model servislerinin bağlanması gerekiyor.'
                        : 'Hazır vaka dosyaları bulunamadı veya geçerli değil. Demo paketinin hazırlanması gerekiyor.'}
                    </EmptyState>
                  </div>
                ) : !record ? (
                  <div className="panel">
                    <EmptyState icon={<FolderOpen />} title="Henüz vaka yok">
                      Bu veri kaynağında görüntülenecek vaka bulunmuyor.
                    </EmptyState>
                  </div>
                ) : genomicsRecord ? (
                  <GenomicsWorkspace
                    key={`${mode}:${genomicsRecord.id}`}
                    record={genomicsRecord}
                  />
                ) : view === 'imaging' ? (
                  <ImagingWorkspace
                    key={`${mode}:${record.id}`}
                    record={record as CaseRecord}
                  />
                ) : (
                  <section className="panel genomics-panel">
                    <div className="panel-heading">
                      <span>
                        <Dna size={18} /> Varyant patojenite tahmini
                      </span>
                      <span className="small muted">XGBoost</span>
                    </div>
                    <EmptyState
                      icon={<Dna size={34} />}
                      title="Bu görüntü vakasının varyant kaydı yok"
                      action={
                        <button className="ghost" onClick={() => changeModule('genomics')}>
                          Genomik vakalara geç <ArrowRight size={16} />
                        </button>
                      }
                    >
                      Bu MR vakasıyla eşleştirilmiş bir varyant bulunmuyor. Hazır genomik
                      vakalar kenar çubuğundaki <strong>Genomik</strong> modülünde; onlar ayrı
                      kayıtlardır, bu hastaya ait değildir.
                    </EmptyState>
                    <div className="notice">
                      <Info size={16} />
                      <span>
                        Görüntü ve genomik veriler yalnızca doğrulanmış vaka eşleşmesiyle birlikte
                        gösterilir.
                      </span>
                    </div>
                  </section>
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
              <span>Onkolojide 3T · Araştırma ve gösterim amaçlı</span>
            </footer>
          </main>
        </div>
      </div>
    </div>
  );
}
