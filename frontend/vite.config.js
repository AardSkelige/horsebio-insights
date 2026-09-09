import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// В Docker бэкенд — сосед по сети (compose подставляет http://backend:8000),
// на хосте он слушает 8001. Один конфиг вместо двух: разъезжались молча.
const apiTarget = process.env.VITE_API_TARGET || 'http://127.0.0.1:8001';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
  },
  server: {
    host: '0.0.0.0',
    port: 3001,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        secure: false,
      },
      '/parser': {
        target: apiTarget,
        changeOrigin: true,
        secure: false,
      }
    }
  }
});
