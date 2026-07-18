import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// Inside the compose network the backend is reachable as `backend`; a bare
// `npm run dev` on the host uses the published localhost port instead.
const inContainer = existsSync('/run/.containerenv') || existsSync('/.dockerenv')
const apiProxyTarget =
  process.env.KANDIDLY_API_PROXY ?? (inContainer ? 'http://backend:8000' : 'http://localhost:8000')

// Tailwind v3 + Vite doesn't reliably invalidate compiled CSS when the
// Tailwind/PostCSS config changes (source/CSS edits hot-reload fine, config
// edits silently keep the old palette). Restart the dev server on config
// change so the pipeline is rebuilt from scratch.
function restartOnConfigChange(files: string[]): Plugin {
  return {
    name: 'restart-on-config-change',
    configureServer(server) {
      const watched = files.map(f => resolve(f))
      watched.forEach(f => server.watcher.add(f))
      server.watcher.on('change', file => {
        if (watched.includes(resolve(file))) {
          server.config.logger.info(`${file} changed — restarting dev server`, { timestamp: true })
          void server.restart()
        }
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    restartOnConfigChange(['tailwind.config.cjs', 'postcss.config.js']),
  ],
  server: {
    // Phone testing runs the dev server behind an HTTPS tunnel (getUserMedia
    // needs a secure context). Accept the tunnel hostname and proxy the API
    // same-origin — the phone can't reach the laptop's localhost:8000
    // (src/lib/api.ts switches to a relative base on non-localhost hosts).
    allowedHosts: ['.trycloudflare.com'],
    proxy: {
      '/api': { target: apiProxyTarget, changeOrigin: true },
    },
  },
})
