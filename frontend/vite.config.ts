import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// 本地开发时，Vite Dev Server 把 /api 转发给网关（默认 http://localhost:8080），
// 与生产环境经 Traefik 网关访问的路径保持一致，避免前端代码里区分环境拼接不同的 base url。
const gatewayTarget = process.env.VITE_GATEWAY_TARGET ?? 'http://localhost:8080'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text-summary'],
      // 单测管 TS 逻辑；.vue 页面由 e2e 覆盖，main.ts 只做挂载。
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.test.ts', 'src/**/*.d.ts', 'src/main.ts'],
      // 下限与后端一样只升不降，补了测试就调高（工程规范第 5 节）。
      thresholds: { statements: 92, branches: 83, functions: 91, lines: 93 },
    },
  },
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
  build: {
    rollupOptions: {
      output: {
        // 页面已按路由懒加载，主包剩下的几乎全是第三方库。把它们按变更频率分开：
        // 业务代码改动不再让用户重下 Element Plus，三个 chunk 也能并行下载。
        // 首屏总字节没变少，换的是缓存命中和并行度。
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('element-plus') || id.includes('@element-plus')) return 'element-plus'
          // 只有图表页用，单独成块才能跟着页面懒加载；并进 vendor 会让每个页面都多下 500KB。
          if (id.includes('/echarts/') || id.includes('/zrender/')) return 'echarts'
          if (id.includes('/vue/') || id.includes('vue-router') || id.includes('pinia') || id.includes('@vue/')) {
            return 'vue'
          }
          return 'vendor'
        },
      },
    },
  },
})
