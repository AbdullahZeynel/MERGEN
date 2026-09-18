import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LiveWorkspace } from '../components/LiveWorkspace';
import { withLanguage } from './render';
import { makeLiveJob } from './fixtures';

type Call = { url: string; init: RequestInit };
let calls: Call[] = [];

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const session = {
  status: 'active',
  csrfToken: 'token', // repo-guard: allow — test sabiti, sir degil
  idleTimeoutSeconds: 180,
  absoluteExpiresAt: 2_000_000_000,
};

function serve(handler: (call: Call) => Response) {
  calls = [];
  vi.stubGlobal('fetch', (url: string, init: RequestInit = {}) => {
    calls.push({ url, init });
    return Promise.resolve(handler({ url, init }));
  });
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    withLanguage(
      <QueryClientProvider client={client}>
        <LiveWorkspace />
      </QueryClientProvider>,
    ),
  );
  return userEvent.setup();
}

const volume = (name: string) => new File([new Uint8Array(16).fill(3)], name);
const fourVolumes = () => [
  volume('a_T1w.nii.gz'),
  volume('a_T1ce.nii.gz'),
  volume('a_T2w.nii.gz'),
  volume('a_FLAIR.nii.gz'),
];

async function connect(user: ReturnType<typeof mount>) {
  await user.type(screen.getByLabelText('Erişim kodu'), 'kod');
  await user.click(screen.getByRole('button', { name: /Oturum aç/ }));
  await screen.findByRole('button', { name: /Analizi başlat/ });
}

async function chooseAll(user: ReturnType<typeof mount>) {
  const files = fourVolumes();
  for (const [index, modality] of ['T1', 'T1CE', 'T2', 'FLAIR'].entries())
    await user.upload(screen.getByLabelText(modality), files[index]);
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = 'mergen_csrf=; max-age=0';
});

describe('live workspace', () => {
  it('asks for the access code before anything can be uploaded', () => {
    serve(() => json(session));
    mount();
    expect(screen.getByLabelText('Erişim kodu')).toBeInTheDocument();
    expect(screen.queryByLabelText('T1')).not.toBeInTheDocument();
  });

  it('says the access code is wrong instead of showing a prepared case', async () => {
    serve(() => json({ detail: 'no' }, 401));
    const user = mount();
    await user.type(screen.getByLabelText('Erişim kodu'), 'yanlis');
    await user.click(screen.getByRole('button', { name: /Oturum aç/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Erişim kodu geçersiz');
    expect(screen.queryByLabelText('T1')).not.toBeInTheDocument();
  });

  it('keeps the analysis disabled until all four modalities are chosen', async () => {
    serve(() => json(session));
    const user = mount();
    await connect(user);
    const start = screen.getByRole('button', { name: /Analizi başlat/ });
    expect(start).toBeDisabled();
    await user.upload(screen.getByLabelText('T1'), volume('a_T1w.nii.gz'));
    expect(start).toBeDisabled();
    await chooseAll(user);
    expect(start).toBeEnabled();
  });

  it('uploads a zip body and then follows the job to completion', async () => {
    document.cookie = 'mergen_csrf=token';
    const finished = makeLiveJob();
    serve(({ url, init }) => {
      if (url.endsWith('/session') && init.method === 'POST') return json(session);
      if (url.endsWith('/jobs'))
        return json(
          { jobId: finished.jobId, status: 'queued', module: 'imaging', disease: 'glioma' },
          202,
        );
      return json(finished);
    });
    const user = mount();
    await connect(user);
    await chooseAll(user);
    await user.click(screen.getByRole('button', { name: /Analizi başlat/ }));

    await screen.findByText('Tamamlandı');
    const upload = calls.find((call) => call.url.endsWith('/jobs'))!;
    expect((upload.init.headers as Record<string, string>)['Content-Type']).toBe('application/zip');
    expect(upload.init.body).toBeInstanceOf(Blob);
  });

  it('names the model that produced the result so it is not read as the demo one', async () => {
    document.cookie = 'mergen_csrf=token';
    const finished = makeLiveJob();
    serve(({ url, init }) => {
      if (url.endsWith('/session') && init.method === 'POST') return json(session);
      if (url.endsWith('/jobs'))
        return json(
          { jobId: finished.jobId, status: 'queued', module: 'imaging', disease: 'glioma' },
          202,
        );
      return json(finished);
    });
    const user = mount();
    await connect(user);
    await chooseAll(user);
    await user.click(screen.getByRole('button', { name: /Analizi başlat/ }));
    expect(await screen.findByText(/mergen-uwcse v3/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Sonucu indir/ })).toHaveAttribute(
      'href',
      `/api/live/jobs/${finished.jobId}/download`,
    );
  });

  it('offers no download while the job has not finished', async () => {
    document.cookie = 'mergen_csrf=token';
    const running = { ...makeLiveJob(), status: 'running' as const };
    delete (running as Partial<typeof running>).result;
    delete (running as Partial<typeof running>).downloadUrl;
    delete (running as Partial<typeof running>).assetUrls;
    serve(({ url, init }) => {
      if (url.endsWith('/session') && init.method === 'POST') return json(session);
      if (url.endsWith('/jobs'))
        return json(
          { jobId: running.jobId, status: 'queued', module: 'imaging', disease: 'glioma' },
          202,
        );
      return json(running);
    });
    const user = mount();
    await connect(user);
    await chooseAll(user);
    await user.click(screen.getByRole('button', { name: /Analizi başlat/ }));
    await screen.findByText('Model çalışıyor');
    expect(screen.queryByRole('link', { name: /Sonucu indir/ })).not.toBeInTheDocument();
  });

  it('reports a failed job with its code rather than an empty result', async () => {
    document.cookie = 'mergen_csrf=token';
    const failed = {
      ...makeLiveJob(),
      status: 'failed' as const,
      errorCode: 'model-unavailable',
    };
    delete (failed as Partial<typeof failed>).result;
    delete (failed as Partial<typeof failed>).downloadUrl;
    delete (failed as Partial<typeof failed>).assetUrls;
    serve(({ url, init }) => {
      if (url.endsWith('/session') && init.method === 'POST') return json(session);
      if (url.endsWith('/jobs'))
        return json(
          { jobId: failed.jobId, status: 'queued', module: 'imaging', disease: 'glioma' },
          202,
        );
      return json(failed);
    });
    const user = mount();
    await connect(user);
    await chooseAll(user);
    await user.click(screen.getByRole('button', { name: /Analizi başlat/ }));
    expect(await screen.findByText(/model-unavailable/)).toBeInTheDocument();
  });

  it('refuses a rejected volume before it reaches the server', async () => {
    document.cookie = 'mergen_csrf=token';
    serve(({ url, init }) => {
      if (url.endsWith('/session') && init.method === 'POST') return json(session);
      return json({ detail: 'should not be reached' }, 500);
    });
    const user = mount();
    await connect(user);
    await chooseAll(user);
    // Bos bir hacim `accept`ten geciyor; eleyen sey bizim kendi kontrolumuz.
    await user.upload(
      screen.getByLabelText('FLAIR'),
      new File([], 'a_FLAIR.nii.gz'),
    );
    await user.click(screen.getByRole('button', { name: /Analizi başlat/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('FLAIR dosyası boş');
    expect(calls.some((call) => call.url.endsWith('/jobs'))).toBe(false);
  });

  it('runs a second case in the same session without reconnecting', async () => {
    // Sunucu yalniz *aktif* bir isi engelliyor; bitmis is yeni analizi
    // engellemez, yani oturumu kapatmak gerekmemeli.
    document.cookie = 'mergen_csrf=token';
    const finished = makeLiveJob();
    serve(({ url, init }) => {
      if (url.endsWith('/session') && init.method === 'POST') return json(session);
      if (url.endsWith('/jobs'))
        return json(
          { jobId: finished.jobId, status: 'queued', module: 'imaging', disease: 'glioma' },
          202,
        );
      return json(finished);
    });
    const user = mount();
    await connect(user);
    await chooseAll(user);
    await user.click(screen.getByRole('button', { name: /Analizi başlat/ }));
    await screen.findByText('Tamamlandı');

    await user.click(screen.getByRole('button', { name: /Yeni analiz/ }));
    // Erisim kapisina degil, bos yukleme formuna donulur.
    expect(screen.queryByLabelText('Erişim kodu')).not.toBeInTheDocument();
    expect(screen.getAllByText('Dosya seçilmedi')).toHaveLength(4);
    expect(screen.getByRole('button', { name: /Analizi başlat/ })).toBeDisabled();
  });

  it('offers no new analysis while the job is still running', async () => {
    document.cookie = 'mergen_csrf=token';
    const running = { ...makeLiveJob(), status: 'running' as const };
    delete (running as Partial<typeof running>).result;
    delete (running as Partial<typeof running>).downloadUrl;
    delete (running as Partial<typeof running>).assetUrls;
    serve(({ url, init }) => {
      if (url.endsWith('/session') && init.method === 'POST') return json(session);
      if (url.endsWith('/jobs'))
        return json(
          { jobId: running.jobId, status: 'queued', module: 'imaging', disease: 'glioma' },
          202,
        );
      return json(running);
    });
    const user = mount();
    await connect(user);
    await chooseAll(user);
    await user.click(screen.getByRole('button', { name: /Analizi başlat/ }));
    await screen.findByText('Model çalışıyor');
    expect(screen.queryByRole('button', { name: /Yeni analiz/ })).not.toBeInTheDocument();
  });

  it('returns to the access gate when the session is closed', async () => {
    document.cookie = 'mergen_csrf=token';
    serve(({ url, init }) => {
      if (url.endsWith('/session') && init.method === 'DELETE')
        return new Response(null, { status: 204 });
      return json(session);
    });
    const user = mount();
    await connect(user);
    await user.click(screen.getByRole('button', { name: /Oturumu kapat/ }));
    await waitFor(() => expect(screen.getByLabelText('Erişim kodu')).toBeInTheDocument());
    expect(calls.some((call) => call.init.method === 'DELETE')).toBe(true);
  });
});
