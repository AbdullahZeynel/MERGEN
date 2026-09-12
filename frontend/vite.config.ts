import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:9000' } },
  preview: { proxy: { '/api': 'http://127.0.0.1:9000' } },
  optimizeDeps: { entries: ['index.html'] },
  test: { environment: 'jsdom', setupFiles: './src/test/setup.ts', css: false },
});
