import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

const loopbackPorts = new Set([5173, 5174, 5175])
const demoPort = Number.parseInt(process.env.DEMO_FRONTEND_PORT || '', 10)
if (Number.isInteger(demoPort) && demoPort > 0 && demoPort <= 65535) {
  loopbackPorts.add(demoPort)
}
const loopbackOrigins = ['localhost', '127.0.0.1'].flatMap((host) =>
  [...loopbackPorts].map((port) => `http://${host}:${port}`),
)

export default defineConfig(({ mode }) => {
  // This value configures Vite's server-side proxy and must not be exposed to browser code.
  const env = loadEnv(mode, process.cwd(), 'API_PROXY_TARGET')
  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      allowedHosts: ['localhost', '127.0.0.1'],
      cors: {
        origin: loopbackOrigins,
        credentials: false,
      },
      proxy: {
        '/api': {
          target: env.API_PROXY_TARGET || 'http://127.0.0.1:8002',
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: '127.0.0.1',
      strictPort: true,
    },
  }
})
