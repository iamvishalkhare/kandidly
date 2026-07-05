import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

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
})
