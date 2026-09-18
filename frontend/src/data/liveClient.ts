import { z } from 'zod';
import { liveJobSchema, liveReportSchema, type LiveJob, type LiveReport } from './contracts.live';
import type { MessageKey } from '../i18n/messages';

// Canli oturum istemcisi. Tek kural: bu dosya hicbir kosulda demo verisine
// donmez. Canli bir istek basarisiz olursa cagiran taraf `LiveError` alir ve
// kullaniciya ne oldugunu soyler; sessizce hazir bir vaka gostermek, olculmemis
// bir sonucu olculmus gibi okutur.

const BASE = '/api/live';
const CSRF_COOKIE = 'mergen_csrf';
const CSRF_HEADER = 'X-Mergen-CSRF';
const ACCESS_HEADER = 'X-Mergen-Live-Access';
/** Sunucunun bosta kalma esigi 3 dakika; 30 saniye onun guvenli boleni. */
export const HEARTBEAT_INTERVAL_MS = 30_000;

export type LiveErrorCode =
  | 'access-denied'
  | 'not-configured'
  | 'session-expired'
  | 'session-conflict'
  | 'csrf-rejected'
  | 'capacity'
  | 'job-active'
  | 'bundle-rejected'
  | 'bundle-too-large'
  | 'bundle-unsupported'
  | 'result-integrity'
  | 'contract'
  | 'network'
  | 'unexpected';

export const liveErrorKeys: Record<LiveErrorCode, MessageKey> = {
  'access-denied': 'live.error.accessDenied',
  'not-configured': 'live.error.notConfigured',
  'session-expired': 'live.error.sessionExpired',
  'session-conflict': 'live.error.sessionConflict',
  'csrf-rejected': 'live.error.csrfRejected',
  capacity: 'live.error.capacity',
  'job-active': 'live.error.jobActive',
  'bundle-rejected': 'live.error.bundleRejected',
  'bundle-too-large': 'live.error.bundleTooLarge',
  'bundle-unsupported': 'live.error.bundleUnsupported',
  'result-integrity': 'live.error.resultIntegrity',
  contract: 'live.error.contract',
  network: 'live.error.network',
  unexpected: 'live.error.unexpected',
};

export class LiveError extends Error {
  readonly code: LiveErrorCode;
  /** 429 icin sunucunun verdigi bekleme suresi; yoksa undefined. */
  readonly retryAfterSeconds?: number;

  constructor(code: LiveErrorCode, retryAfterSeconds?: number) {
    super(code);
    this.name = 'LiveError';
    this.code = code;
    this.retryAfterSeconds = retryAfterSeconds;
  }

  get messageKey(): MessageKey {
    return liveErrorKeys[this.code];
  }
}

const sessionSchema = z.object({
  status: z.literal('active'),
  csrfToken: z.string().min(1).nullish(),
  idleTimeoutSeconds: z.number().int().positive(),
  absoluteExpiresAt: z.number().int().nonnegative(),
});
const heartbeatSchema = z.object({
  status: z.literal('active'),
  lastSeen: z.number().int().nonnegative(),
});
const acceptedJobSchema = z.object({
  jobId: z.string().regex(/^[a-f0-9]{32}$/),
  status: z.literal('queued'),
  module: z.literal('imaging'),
  disease: z.literal('glioma'),
});

export type LiveSession = z.infer<typeof sessionSchema>;
export type AcceptedJob = z.infer<typeof acceptedJobSchema>;

/** CSRF cerezi HttpOnly degildir; oturum cerezi okunamaz ve okunmasi gerekmez. */
export function readCsrfToken(): string | null {
  for (const entry of document.cookie.split(';')) {
    const [name, ...rest] = entry.trim().split('=');
    if (name === CSRF_COOKIE && rest.length) return decodeURIComponent(rest.join('='));
  }
  return null;
}

function retryAfter(response: Response): number | undefined {
  const raw = Number(response.headers.get('Retry-After'));
  return Number.isFinite(raw) && raw > 0 ? raw : undefined;
}

// Ayni HTTP kodu farkli uclarda farkli sey anlatiyor: /session uzerindeki 401
// "erisim kodu yanlis", digerlerindeki 401 "oturum dustu".
function failureFor(response: Response, opening: boolean): LiveError {
  switch (response.status) {
    case 401:
      return new LiveError(opening ? 'access-denied' : 'session-expired');
    case 403:
      return new LiveError('csrf-rejected');
    case 409:
      return new LiveError(opening ? 'session-conflict' : 'job-active');
    case 413:
      return new LiveError('bundle-too-large');
    case 415:
      return new LiveError('bundle-unsupported');
    case 422:
      return new LiveError('bundle-rejected');
    case 429:
      return new LiveError('capacity', retryAfter(response));
    case 503:
      return new LiveError(opening ? 'not-configured' : 'result-integrity');
    default:
      return new LiveError('unexpected');
  }
}

async function call(path: string, init: RequestInit, opening = false): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { credentials: 'same-origin', cache: 'no-store', ...init });
  } catch (error) {
    // AbortError cagiranin kendi karari; hata olarak sarmalanmaz.
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new LiveError('network');
  }
  if (!response.ok) throw failureFor(response, opening);
  return response;
}

async function parsed<T>(response: Response, schema: z.ZodType<T>): Promise<T> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new LiveError('contract');
  }
  const result = schema.safeParse(body);
  if (!result.success) throw new LiveError('contract');
  return result.data;
}

function mutationHeaders(csrfToken: string, extra: Record<string, string> = {}) {
  return { [CSRF_HEADER]: csrfToken, ...extra };
}

export async function openSession(accessCode: string, signal?: AbortSignal): Promise<LiveSession> {
  const response = await call(
    '/session',
    { method: 'POST', signal, headers: { [ACCESS_HEADER]: accessCode } },
    true,
  );
  return parsed(response, sessionSchema);
}

export async function sessionStatus(signal?: AbortSignal): Promise<LiveSession> {
  return parsed(await call('/session', { method: 'GET', signal }), sessionSchema);
}

export async function heartbeat(csrfToken: string, signal?: AbortSignal): Promise<number> {
  const response = await call('/session/heartbeat', {
    method: 'POST',
    signal,
    headers: mutationHeaders(csrfToken),
  });
  return (await parsed(response, heartbeatSchema)).lastSeen;
}

export async function closeSession(csrfToken: string): Promise<void> {
  await call('/session', { method: 'DELETE', headers: mutationHeaders(csrfToken) });
}

export async function submitJob(
  bundle: Blob,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<AcceptedJob> {
  const response = await call('/jobs', {
    method: 'POST',
    signal,
    headers: mutationHeaders(csrfToken, { 'Content-Type': 'application/zip' }),
    body: bundle,
  });
  return parsed(response, acceptedJobSchema);
}

export async function jobStatus(jobId: string, signal?: AbortSignal): Promise<LiveJob> {
  const response = await call(`/jobs/${jobId}`, { method: 'GET', signal });
  return parsed(response, liveJobSchema);
}

/**
 * Sonuc ZIP'inin icindeki `report.json`. Yol her zaman isin kendi varlik
 * baglantisidir: `liveJobSchema` onu isin kanonik yoluna bagladigi icin burada
 * gelen adres baska bir ise ait olamaz.
 */
export async function fetchReport(assetUrl: string, signal?: AbortSignal): Promise<LiveReport> {
  let response: Response;
  try {
    response = await fetch(assetUrl, { credentials: 'same-origin', cache: 'no-store', signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new LiveError('network');
  }
  if (!response.ok) throw failureFor(response, false);
  return parsed(response, liveReportSchema);
}

/**
 * Sunucu son etkinlikten 3 dakika sonra oturumu kapatir, sekme kapanmasi
 * guvenilir bir olay degil. Bu yuzden heartbeat zorunlu: durdugu anda oturumun
 * suresi isler. Oturum dustugunde (`session-expired`) zamanlayici kendini
 * durdurur; yeniden denemek yalnizca sureyi uzatirdi.
 */
export function startHeartbeat(
  csrfToken: string,
  onLost: (error: LiveError) => void,
  intervalMs: number = HEARTBEAT_INTERVAL_MS,
): () => void {
  let stopped = false;
  const timer = setInterval(() => {
    void heartbeat(csrfToken).catch((error: unknown) => {
      if (stopped) return;
      const failure = error instanceof LiveError ? error : new LiveError('unexpected');
      stop();
      onLost(failure);
    });
  }, intervalMs);
  const stop = () => {
    if (stopped) return;
    stopped = true;
    clearInterval(timer);
  };
  return stop;
}
