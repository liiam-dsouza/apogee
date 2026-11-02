/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    rolldownOptions: {
      output: {
        // The MapLibre worker ships as .mjs. Emit it as .js: every server types .js as
        // JavaScript (nginx's stock table has no .mjs, which stopped all map layers),
        // and the new name escapes any year-long cached copy of the mistyped .mjs.
        assetFileNames: (asset) =>
          asset.names.some((n) => n.endsWith('.mjs')) ? 'assets/[name]-[hash].js' : 'assets/[name]-[hash][extname]',
      },
    },
  },
  server: {
    // The browser talks only to the API; in dev, proxy to a local uvicorn.
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
  test: {
    environment: 'jsdom',
    // e2e/ is Playwright's.
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
