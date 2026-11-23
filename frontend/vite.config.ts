import { createReadStream, readdirSync, readFileSync } from 'node:fs'
import { basename, join } from 'node:path'
import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import type { Plugin } from 'vite'
import { defineConfig } from 'vitest/config'

// 本地开发时，Vite Dev Server 把 /api 转发给网关（默认 http://localhost:8080），
// 与生产环境经 Traefik 网关访问的路径保持一致，避免前端代码里区分环境拼接不同的 base url。
const gatewayTarget = process.env.VITE_GATEWAY_TARGET ?? 'http://localhost:8080'

// PDF.js 的 CMap（中文 PDF 没嵌字体时靠它出字）、标准字体、图片解码 wasm 跟着前端一起发布，不走外网 CDN。
// 放在 assets 下、路径带版本号：nginx 对 /assets/ 长期缓存，升级 pdfjs-dist 换路径即可。
const pdfjsRoot = fileURLToPath(new URL('./node_modules/pdfjs-dist', import.meta.url))
const pdfjsVersion = (JSON.parse(readFileSync(join(pdfjsRoot, 'package.json'), 'utf8')) as { version: string }).version
const pdfjsBase = `assets/pdfjs-${pdfjsVersion}`
const PDFJS_ASSET_DIRS = ['cmaps', 'standard_fonts', 'wasm', 'iccs']

function pdfjsAssets(): Plugin {
  return {
    name: 'pdfjs-assets',
    generateBundle() {
      for (const dir of PDFJS_ASSET_DIRS) {
        for (const name of readdirSync(join(pdfjsRoot, dir))) {
          this.emitFile({ type: 'asset', fileName: `${pdfjsBase}/${dir}/${name}`, source: readFileSync(join(pdfjsRoot, dir, name)) })
        }
      }
    },
    configureServer(server) {
      server.middlewares.use(`/${pdfjsBase}`, (req, res, next) => {
        const [dir = '', name = ''] = (req.url ?? '').split('?')[0]!.split('/').filter(Boolean)
        if (!PDFJS_ASSET_DIRS.includes(dir) || name.startsWith('.') || name !== basename(name)) return next()
        createReadStream(join(pdfjsRoot, dir, name)).on('error', () => next()).pipe(res)
      })
    },
  }
}

// 第三方库按变更频率分块，按顺序取第一个命中的。
const VENDOR_CHUNKS: [string, string[]][] = [
  ['element-plus', ['element-plus', '@element-plus']],
  // 只有图表页用，单独成块才能跟着页面懒加载；并进 vendor 会让每个页面都多下 500KB。
  ['echarts', ['/echarts/', '/zrender/']],
  ['vue', ['/vue/', 'vue-router', 'pinia', '@vue/']],
]

export default defineConfig({
  plugins: [vue(), pdfjsAssets()],
  define: {
    __PDFJS_ASSET_BASE__: JSON.stringify(`/${pdfjsBase}/`),
  },
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
      thresholds: { statements: 93, branches: 85, functions: 91, lines: 94 },
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
        // PDF.js 的 worker 是 .mjs：nginx 的 mime.types 不一定认 .mjs，按 octet-stream 下发的话浏览器拒绝当模块 worker 执行。
        assetFileNames: info => (info.names[0]?.endsWith('.mjs') ? 'assets/[name]-[hash].js' : 'assets/[name]-[hash][extname]'),
        // 页面已按路由懒加载，主包剩下的几乎全是第三方库。把它们按变更频率分开：
        // 业务代码改动不再让用户重下 Element Plus，三个 chunk 也能并行下载。
        // 首屏总字节没变少，换的是缓存命中和并行度。
        manualChunks(id) {
          // PDF.js 只有知识库预览页经动态 import 用到，交给自动分块，它自己就是一个懒加载块。
          // 手动分组的话 pdf.mjs 依赖的 Vite 预加载辅助函数会被一起拉进去，首页为它静态引用整个 PDF.js（400KB）。
          if (!id.includes('node_modules') || id.includes('/pdfjs-dist/')) return
          return VENDOR_CHUNKS.find(([, marks]) => marks.some(mark => id.includes(mark)))?.[0] ?? 'vendor'
        },
      },
    },
  },
})
