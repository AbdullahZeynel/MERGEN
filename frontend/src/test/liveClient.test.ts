import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  closeSession,
  heartbeat,
  jobStatus,
  liveErrorKeys,
  LiveError,
  openSession,
  readCsrfToken,
  startHeartbeat,
  submitJob,
} from '../data/liveClient';
import { tr } from '../i18n/messages';
import { makeLiveJob } from './fixtures';

type Call = { url: string; init: RequestInit };
let calls: Call[] = [];

const respond = (body: unknown, init: ResponseInit = {}) =>
  new Response(body === undefined ? null : JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });

function serve(handler: (call: Call) => Response | Promise<Response>) {
  vi.stubGlobal('fetch', (url: string, init: RequestInit = {}) => {
    const call = { url, init };
    calls.push(call);
    return Promise.resolve(handler(call));
  });
}

const activeSession = {
  status: 'active',
  csrfToken: 'csrf-token', // repo-guard: allow — sozlesme fixture'i, sir degil
  idleTimeoutSeconds: 180,
  absoluteExpiresAt: 1_758_000_600,
};

beforeEach(() => {
  calls = [];
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('live session client', () => {
  it('sends the access code when it opens a session, and nowhere else', async () => {
    serve(({ url }) =>
      url.endsWith('/session/heartbeat')
        ? respond({ status: 'active', lastSeen: 1 })
        : respond(activeSession),
    );
    await openSession('kod-1234');
    expect(calls[0].url).toBe('/api/live/session');
    expect((calls[0].init.headers as Record<string, string>)['X-Mergen-Live-Access']).toBe('kod-1234');

    await heartbeat('csrf-token');
    const headers = (calls[1].init.headers ?? {}) as Record<string, string>;
    expect(headers['X-Mergen-Live-Access']).toBeUndefined();
    expect(headers['X-Mergen-CSRF']).toBe('csrf-token');
  });

  it('puts the CSRF token on every mutation and on no read', async () => {
    serve(({ url }) =>
      url.endsWith('/session/heartbeat')
        ? respond({ status: 'active', lastSeen: 1 })
        : url.includes('/jobs/')
          ? respond(makeLiveJob())
          : url.endsWith('/jobs')
            ? respond(
                { jobId: 'a'.repeat(32), status: 'queued', module: 'imaging', disease: 'glioma' },
                { status: 202 },
              )
            : respond(undefined, { status: 204 }),
    );
    await heartbeat('t');
    await submitJob(new Blob(['x']), 't');
    await closeSession('t');
    await jobStatus('a'.repeat(32));
    const header = (index: number) =>
      ((calls[index].init.headers ?? {}) as Record<string, string>)['X-Mergen-CSRF'];
    expect([header(0), header(1), header(2)]).toEqual(['t', 't', 't']);
    expect(header(3)).toBeUndefined();
  });

  it('declares the bundle as a zip body, not a form', async () => {
    serve(() =>
      respond(
        { jobId: 'a'.repeat(32), status: 'queued', module: 'imaging', disease: 'glioma' },
        { status: 202 },
      ),
    );
    await submitJob(new Blob(['zip-bytes']), 't');
    expect((calls[0].init.headers as Record<string, string>)['Content-Type']).toBe('application/zip');
    expect(calls[0].init.body).toBeInstanceOf(Blob);
  });

  it('separates a wrong access code from a dropped session', async () => {
    serve(() => respond({ detail: 'no' }, { status: 401 }));
    await expect(openSession('wrong')).rejects.toMatchObject({ code: 'access-denied' });
    await expect(heartbeat('t')).rejects.toMatchObject({ code: 'session-expired' });
  });

  it('separates a busy server from a session that already has a job', async () => {
    serve(() => respond({ detail: 'no' }, { status: 409 }));
    await expect(openSession('kod')).rejects.toMatchObject({ code: 'session-conflict' });
    await expect(submitJob(new Blob(['x']), 't')).rejects.toMatchObject({ code: 'job-active' });
  });

  it('carries the server retry delay on a capacity refusal', async () => {
    serve(() => respond({ detail: 'full' }, { status: 429, headers: { 'Retry-After': '60' } }));
    await expect(openSession('kod')).rejects.toMatchObject({
      code: 'capacity',
      retryAfterSeconds: 60,
    });
  });

  it('maps the upload refusals the backend really returns', async () => {
    for (const [status, code] of [
      [413, 'bundle-too-large'],
      [415, 'bundle-unsupported'],
      [422, 'bundle-rejected'],
    ] as const) {
      serve(() => respond({ detail: 'no' }, { status }));
      await expect(submitJob(new Blob(['x']), 't')).rejects.toMatchObject({ code });
    }
  });

  it('refuses a job that does not satisfy the contract instead of showing it', async () => {
    // Referans etiketi tasiyan bir canli sonuc ekrana Dice cikarirdi.
    const job = makeLiveJob();
    job.result!.hasGroundTruth = true as unknown as false;
    serve(() => respond(job));
    await expect(jobStatus('a'.repeat(32))).rejects.toMatchObject({ code: 'contract' });
  });

  it('reports an unreachable server as a network failure, not as an empty result', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('failed to fetch')));
    await expect(jobStatus('a'.repeat(32))).rejects.toMatchObject({ code: 'network' });
  });

  it('lets an abort through untouched so a cancel is not read as an error', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.reject(new DOMException('aborted', 'AbortError')),
    );
    await expect(jobStatus('a'.repeat(32))).rejects.toThrow(DOMException);
  });

  it('gives every failure a dictionary message', () => {
    for (const [code, key] of Object.entries(liveErrorKeys)) {
      expect(new LiveError(code as never).messageKey).toBe(key);
      expect(tr[key].trim()).not.toBe('');
    }
  });

  it('reads the CSRF cookie and ignores every other cookie', () => {
    document.cookie = 'other=1';
    document.cookie = 'mergen_csrf=abc%20def';
    expect(readCsrfToken()).toBe('abc def');
  });
});

describe('heartbeat', () => {
  it('keeps beating on the interval the session needs', async () => {
    vi.useFakeTimers();
    serve(() => respond({ status: 'active', lastSeen: 1 }));
    const stop = startHeartbeat('t', () => {}, 30_000);
    await vi.advanceTimersByTimeAsync(90_000);
    expect(calls).toHaveLength(3);
    stop();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(calls).toHaveLength(3);
  });

  it('stops itself when the session is gone and says so once', async () => {
    // Dusmus bir oturuma vurmaya devam etmek yalnizca ayni hatayi tekrarlar.
    vi.useFakeTimers();
    serve(() => respond({ detail: 'gone' }, { status: 401 }));
    const lost = vi.fn();
    startHeartbeat('t', lost, 30_000);
    await vi.advanceTimersByTimeAsync(120_000);
    expect(lost).toHaveBeenCalledTimes(1);
    expect(lost.mock.calls[0][0]).toMatchObject({ code: 'session-expired' });
    expect(calls).toHaveLength(1);
  });
});

describe('the live client never falls back to demo data', () => {
  it('imports nothing from the demo source', async () => {
    const source = (await import('../data/liveClient?raw')).default as unknown as string;
    expect(source).not.toContain('/api/demo');
    expect(source).not.toContain('demoSource');
  });
});
