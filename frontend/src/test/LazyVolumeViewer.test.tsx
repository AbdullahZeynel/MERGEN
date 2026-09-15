import { act, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.doUnmock('../components/VolumeViewer');
  vi.resetModules();
});

it('announces an accessible busy state while the 3D chunk loads', async () => {
  let finishLoading!: (module: { VolumeViewer: () => React.JSX.Element }) => void;
  vi.doMock(
    '../components/VolumeViewer',
    () =>
      new Promise((resolve) => {
        finishLoading = resolve;
      }),
  );
  const { LazyVolumeViewer } = await import('../components/LazyVolumeViewer');

  render(<LazyVolumeViewer url="/demo.glb" />);

  const status = screen.getByRole('status');
  expect(status).toHaveAttribute('aria-live', 'polite');
  expect(status.closest('.mesh-stage')).toHaveAttribute('aria-busy', 'true');
  expect(screen.getByRole('heading', { name: '3D görüntüleyici hazırlanıyor…' })).toBeVisible();

  await vi.waitFor(() => expect(finishLoading).toBeTypeOf('function'));
  await act(async () => {
    finishLoading({ VolumeViewer: () => <div>3D görüntüleyici hazır</div> });
  });
  expect(await screen.findByText('3D görüntüleyici hazır')).toBeVisible();
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});
