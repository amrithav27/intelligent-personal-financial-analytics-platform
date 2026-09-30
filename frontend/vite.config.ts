import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: 'https://localhost:443',
        changeOrigin: true,
        secure: false,
        rejectUnauthorized: false,
        cookieDomainRewrite: 'localhost:3000',
      },
      '/ws': {
        target: 'wss://localhost:443',
        changeOrigin: true,
        secure: false,
        rejectUnauthorized: false,
        ws: true,
      },
    },
  },
})
