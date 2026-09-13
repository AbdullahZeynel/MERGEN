import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';
import { loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const apiUrl = loadEnv(mode, '.', 'MERGEN_').MERGEN_API_URL ?? 'http://127.0.0.1:9000';

  return {
  plugins: [react()],
  server: { proxy: { '/api': apiUrl } },
  preview: { proxy: { '/api': apiUrl } },
  optimizeDeps: { entries: ['index.html'] },
  test: { environment: 'jsdom', setupFiles: './src/test/setup.ts', css: false },
  };
});
