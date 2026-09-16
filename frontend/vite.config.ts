import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 本地开发时，Vite Dev Server 把 /api 转发给网关（默认 http://localhost:8080），
// 与生产环境经 Traefik 网关访问的路径保持一致，避免前端代码里区分环境拼接不同的 base url。
const gatewayTarget = process.env.VITE_GATEWAY_TARGET ?? 'http://localhost:8080'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: gatewayTarget,
        changeOrigin: true,
      },
    },
  },
})
