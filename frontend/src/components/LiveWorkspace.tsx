import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Box, Download, LogOut, RotateCcw, ShieldCheck, Upload } from 'lucide-react';
import {
  closeSession,
  fetchReport,
  jobStatus,
  LiveError,
  openSession,
  readCsrfToken,
  startHeartbeat,
  submitJob,
  type LiveSession,
} from '../data/liveClient';
import { buildBundle, BundleRejected, MODALITIES, type Modality, type VolumeSelection } from '../data/liveBundle';
import { liveStatusKeys, type LiveJob, type ReviewFlag } from '../data/contracts';
import { LazyVolumeViewer } from './LazyVolumeViewer';
import { ViewerFrame } from './ViewerFrame';
import { useLanguage } from '../i18n';
import type { MessageKey } from '../i18n/messages';

// Canli calisma alani. Demo tarafiyla hicbir veri paylasmaz: burada bir sey
// yanlis giderse ekranda hata durur, hazir bir vaka belirmez.

const TERMINAL = new Set(['completed', 'failed', 'cancelled']);

type Failure = { key: MessageKey; values?: Record<string, string | number> };

const REVIEW_REASON_KEYS: Record<string, MessageKey> = {
  non_enhancing_tumor: 'live.flag.nonEnhancingTumor',
};

function ReviewFlags({ flags }: { flags: ReviewFlag[] }) {
  const { language, t } = useLanguage();
  const number = (value: number) => value.toLocaleString(language);
  if (flags.length === 0) return null;
  return (
    <ul className="live-flags">
      {flags.map((flag, index) => {
        const known = REVIEW_REASON_KEYS[flag.reason];
        return (
          <li key={`${flag.reason}-${index}`}>
            <AlertTriangle size={17} aria-hidden />
            <div>
              <p>{known ? t(known) : t('live.flag.unknown')}</p>
              <p className="live-note">
                {t('live.flag.evidence', {
                  core: number(flag.evidence.tumor_core_voxels),
                  enhancing: number(flag.evidence.enhancing_voxels),
                  threshold: number(flag.evidence.enhancing_threshold),
                })}
              </p>
              {!known && <p className="live-note">{flag.message}</p>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function failureOf(error: unknown): Failure {
  if (error instanceof BundleRejected)
    return { key: error.messageKey, values: error.modality ? { modality: error.modality } : undefined };
  if (error instanceof LiveError) return { key: error.messageKey };
  return { key: 'live.error.unexpected' };
}

export function LiveWorkspace() {
  const { language, t } = useLanguage();
  const [session, setSession] = useState<LiveSession | null>(null);
  const [accessCode, setAccessCode] = useState('');
  const [selection, setSelection] = useState<VolumeSelection>({});
  const [jobId, setJobId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const stopHeartbeat = useRef<(() => void) | null>(null);

  const endSession = useCallback(() => {
    stopHeartbeat.current?.();
    stopHeartbeat.current = null;
    setSession(null);
    setJobId(null);
    setSelection({});
  }, []);

  // Oturum dusunce is izleme de durur: dusmus bir oturumun isi okunamaz ve
  // okunmaya calisilmasi kullaniciya ayni hatayi tekrar tekrar gosterir.
  useEffect(() => () => stopHeartbeat.current?.(), []);

  const job = useQuery<LiveJob>({
    queryKey: ['live-job', jobId],
    enabled: jobId !== null && session !== null,
    queryFn: ({ signal }) => jobStatus(jobId!, signal),
    refetchInterval: (query) =>
      query.state.data && TERMINAL.has(query.state.data.status) ? false : 2000,
    retry: false,
  });

  useEffect(() => {
    if (job.error) {
      setFailure(failureOf(job.error));
      if (job.error instanceof LiveError && job.error.code === 'session-expired') endSession();
    }
  }, [job.error, endSession]);

  const connect = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      const opened = await openSession(accessCode);
      setSession(opened);
      setAccessCode('');
      const csrf = opened.csrfToken ?? readCsrfToken();
      if (csrf)
        stopHeartbeat.current = startHeartbeat(csrf, (lost) => {
          setFailure({ key: lost.messageKey });
          endSession();
        });
    } catch (error) {
      setFailure(failureOf(error));
    } finally {
      setBusy(false);
    }
  };

  const analyse = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      const csrf = readCsrfToken();
      if (!csrf) throw new LiveError('csrf-rejected');
      const accepted = await submitJob(await buildBundle(selection), csrf);
      setJobId(accepted.jobId);
    } catch (error) {
      setFailure(failureOf(error));
    } finally {
      setBusy(false);
    }
  };

  const leave = async () => {
    const csrf = readCsrfToken();
    try {
      if (csrf) await closeSession(csrf);
    } catch {
      // Oturum zaten dusmus olabilir; kullanici acisindan sonuc ayni.
    } finally {
      endSession();
    }
  };

  const again = () => {
    setJobId(null);
    setSelection({});
    setFailure(null);
  };

  const pick = (modality: Modality, file: File | undefined) =>
    setSelection((current) => ({ ...current, [modality]: file }));

  const result = job.data?.status === 'completed' ? job.data : null;
  const reportUrl = result?.assetUrls?.['report.json'];
  const meshUrl = result?.assetUrls?.['prediction.glb'];
  const report = useQuery({
    queryKey: ['live-report', reportUrl],
    enabled: reportUrl !== undefined,
    queryFn: ({ signal }) => fetchReport(reportUrl!, signal),
    retry: false,
  });
  // Is bittiginde (basarili ya da degil) oturum acik kalir; ayni oturumda
  // yeni bir vaka calistirilabilir.
  const finished = job.data !== undefined && TERMINAL.has(job.data.status);
  const chosen = MODALITIES.filter((modality) => selection[modality]).length;

  return (
    <section className="live-workspace" aria-label={t('live.title')}>
      <header className="live-head">
        <h2>{t('live.title')}</h2>
        <p>{t('live.privacy')}</p>
      </header>

      {failure && (
        <p className="live-failure" role="alert">
          {t(failure.key, failure.values)}
        </p>
      )}

      {!session ? (
        <form className="live-gate" onSubmit={connect}>
          <label htmlFor="live-access">{t('live.accessLabel')}</label>
          <input
            id="live-access"
            type="password"
            autoComplete="off"
            value={accessCode}
            onChange={(event) => setAccessCode(event.target.value)}
            required
          />
          <button type="submit" disabled={busy || accessCode.trim() === ''}>
            <ShieldCheck size={17} /> {t('live.connect')}
          </button>
          <p className="live-note">{t('live.accessNote')}</p>
        </form>
      ) : !jobId ? (
        <form className="live-upload" onSubmit={analyse}>
          <ul className="live-slots">
            {MODALITIES.map((modality) => (
              <li key={modality}>
                <label htmlFor={`volume-${modality}`}>{modality}</label>
                <input
                  id={`volume-${modality}`}
                  type="file"
                  accept=".nii,.nii.gz"
                  onChange={(event) => pick(modality, event.target.files?.[0])}
                />
                <span className="live-slot-state">
                  {selection[modality] ? t('live.slotChosen') : t('live.slotEmpty')}
                </span>
              </li>
            ))}
          </ul>
          <div className="live-actions">
            <button type="submit" disabled={busy || chosen !== MODALITIES.length}>
              <Upload size={17} /> {t('live.analyse')}
            </button>
            <button type="button" className="ghost" onClick={leave}>
              <LogOut size={17} /> {t('live.leave')}
            </button>
          </div>
          <p className="live-note">{t('live.uploadNote')}</p>
        </form>
      ) : (
        <div className="live-progress">
          <p className="live-state">
            <strong>{t(job.data ? liveStatusKeys[job.data.status] : 'live.state.starting')}</strong>
          </p>
          {job.data?.status === 'failed' && job.data.errorCode && (
            <p className="live-note">{t('live.failedWith', { code: job.data.errorCode })}</p>
          )}
          {result && (
            <div className="live-result">
              <p className="live-note">
                {t('live.producedBy', {
                  modelId: result.result!.modelId,
                  modelVersion: result.result!.modelVersion,
                })}
              </p>
              <ViewerFrame title={t('viewer.mesh')} icon={<Box size={18} />}>
                <LazyVolumeViewer url={meshUrl} fallbackHint="mesh.liveFallbackHint" />
              </ViewerFrame>
              {report.isError ? (
                <p className="live-note" role="status">
                  {t('live.reportUnreadable')}
                </p>
              ) : report.data ? (
                <>
                  <table className="live-volumes">
                    <caption>{t('live.volumesCaption')}</caption>
                    <tbody>
                      {(['TC', 'WT', 'ET'] as const).map((region) => (
                        <tr key={region}>
                          <th scope="row">{t(`live.region.${region}` as MessageKey)}</th>
                          <td>{report.data.regionVolumes[region].toLocaleString(language)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <ReviewFlags flags={report.data.reviewFlags} />
                  <p className="live-note">{t('live.noReference')}</p>
                </>
              ) : null}
              <a className="live-download" href={result.downloadUrl} download>
                <Download size={17} /> {t('live.download')}
              </a>
            </div>
          )}
          <div className="live-actions">
            {finished && (
              <button type="button" onClick={again}>
                <RotateCcw size={17} /> {t('live.newAnalysis')}
              </button>
            )}
            <button type="button" className="ghost" onClick={leave}>
              <LogOut size={17} /> {t('live.leave')}
            </button>
          </div>
          <p className="live-note">{t('live.retention')}</p>
        </div>
      )}
    </section>
  );
}
