// frontend/vite.config.docker.js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
    plugins: [react()],
    server: {
        host: '0.0.0.0',
        port: 3001,
        proxy: {
            '/api': {
                target: 'http://backend_nginx:8001',
                changeOrigin: true,
                secure: false
            },
            '/parser': {
                target: 'http://backend_nginx:8001',
                changeOrigin: true,
                secure: false
            }
        }
    }
});