import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// jsdom <dialog> acma/kapama uygulamiyor. Erisilebilirlik agacinin dogru
// olmasi icin `open` niteligi yeterli; modal davranisi burada test edilmiyor.
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute('open', '');
  };
}
if (!HTMLDialogElement.prototype.close) {
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute('open');
  };
}

afterEach(() => {
  cleanup();
});
