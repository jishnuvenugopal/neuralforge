import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// `bash start.sh --dev` runs this dev server; the backend still owns /api and /ws.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    allowedHosts: ['neuralforge.localhost'],
    proxy: {
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
      '/api': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    }
  }
})
