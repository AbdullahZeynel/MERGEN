import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { ViewerFrame } from '../components/ViewerFrame';
import { renderWithLanguage } from './render';

it('opens an accessible dialog and closes on Escape without closing the assistant', async () => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute('open', '');
  };
  const onEscape = vi.fn();
  document.addEventListener('keydown', onEscape);
  const user = userEvent.setup();
  renderWithLanguage(
    <ViewerFrame title="3D segmentasyon" icon={null}>
      <p>Mesh</p>
    </ViewerFrame>,
  );
  await user.click(screen.getByRole('button', { name: '3D segmentasyon büyüt' }));
  expect(screen.getByRole('dialog')).toHaveClass('viewer-dialog');
  expect(document.body.style.overflow).toBe('hidden');
  onEscape.mockClear();
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(document.body.style.overflow).toBe('');
  expect(onEscape).not.toHaveBeenCalled();
  document.removeEventListener('keydown', onEscape);
});
