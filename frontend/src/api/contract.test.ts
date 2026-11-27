import { describe, expect, it, vi } from 'vitest'

const calls = vi.hoisted(() => [] as { method: string; url: string }[])
vi.mock('./http', () => {
  const record = (method: string) => (url: string) => {
    calls.push({ method, url })
    return Promise.resolve({ headers: {}, data: new Blob() })
  }
  return {
    http: { get: record('get'), post: record('post'), put: record('put'), patch: record('patch'), delete: record('delete') },
    request: (promise: Promise<unknown>) => promise.then(() => ({ items: [], total: 0 })),
  }
})
vi.mock('./excelImport', () => ({
  postExcelImport: (url: string) => {
    calls.push({ method: 'post', url })
    return Promise.resolve({})
  },
}))

import * as ai from './ai'
import * as aiBilling from './aiBilling'
import * as aiSamples from './aiSamples'
import * as aiTagging from './aiTagging'
import * as audit from './audit'
import * as auth from './auth'
import * as codebook from './codebook'
import * as crawlerConfig from './crawlerConfig'
import * as crawler from './crawlerMonitoring'
import * as filterOptions from './filterOptions'
import * as policy from './policy'
import * as scenarioCandidates from './scenarioCandidates'
import * as scheduler from './scheduler'
import * as system from './system'
import * as tender from './tender'
import * as thinktank from './thinktank'

type Spec = { paths: Record<string, Record<string, unknown>> }

// frontend 镜像只拷 frontend/，静态 import 仓库根的 docs 会让镜像里的 vue-tsc 找不到模块。
const specs = import.meta.glob<Spec>('../../../docs/openapi/*.json', { eager: true, import: 'default' })

const operations = Object.values(specs).flatMap((spec) =>
  Object.entries(spec.paths).flatMap(([path, methods]) =>
    Object.keys(methods).map((method) => ({
      method,
      pattern: new RegExp(`^${path.replace(/\{[^}]+\}/g, '[^/]+')}$`),
    })),
  ),
)

const modules = {
  ai,
  aiBilling,
  aiSamples,
  aiTagging,
  audit,
  auth,
  codebook,
  crawlerConfig,
  crawler,
  filterOptions,
  policy,
  scenarioCandidates,
  scheduler,
  system,
  tender,
  thinktank,
}

const wrappers = Object.entries(modules).flatMap(([module, exports]) =>
  Object.entries(exports)
    .filter((entry): entry is [string, (...args: unknown[]) => Promise<unknown>] => typeof entry[1] === 'function')
    .map(([name, fn]) => ({ label: `${module}.${name}`, fn })),
)

describe('前端接口封装与后端 OpenAPI 一致', () => {
  it('读到了全部七份 OpenAPI', () => {
    expect(Object.keys(specs)).toHaveLength(7)
  })

  it.each(wrappers)('$label 调用的方法和路径在后端存在', async ({ label, fn }) => {
    calls.length = 0
    if (label.startsWith('tender.list') || label === 'tender.getTenderCount') await fn('purchaser', {})
    else if (label === 'tender.getTenderRecord' || label === 'tender.getTenderContent') await fn('winbid', '123', '0')
    else if (label.startsWith('filterOptions.')) await fn('/policy/sources', 'province_name', '京')
    else if (/^codebook\.(list|create|update|delete|import)ThinktankDicts?$/.test(label)) await fn('file-types', 'id-1', {})
    else if (label === 'thinktank.unfavoriteThinktankItem' || label === 'thinktank.downloadThinktankItemBlob') await fn('reports', 'id-1')
    else await fn('id-1', () => Promise.resolve({}))
    expect(calls.length).toBeGreaterThan(0)
    for (const { method, url } of calls) {
      const path = `/api/v1${url}`
      expect(operations.some((op) => op.method === method && op.pattern.test(path)), `${method.toUpperCase()} ${path}`).toBe(true)
    }
  })

  it('智库 6 张码表的增删改查导入路径与后端 OpenAPI 完全一致', async () => {
    const slugs: codebook.ThinktankDictSlug[] = [
      'file-types',
      'departments',
      'industries',
      'product-types',
      'provinces',
      'market-categories',
    ]
    for (const slug of slugs) {
      calls.length = 0
      await codebook.listThinktankDicts(slug, {})
      await codebook.createThinktankDict(slug, { name: '测试' })
      await codebook.updateThinktankDict(slug, 'id-1', { name: '测试', version: 1 })
      await codebook.deleteThinktankDict(slug, 'id-1')
      await codebook.importThinktankDicts(slug, new File([''], 'a.xlsx'))
      await filterOptions.fetchFilterOptions(`/codebook/thinktank/${slug}`)
      await filterOptions.searchFilterOptions(`/codebook/thinktank/${slug}`, 'name', 'a')
      for (const { method, url } of calls) {
        const path = `/api/v1${url}`
        expect(operations.some((op) => op.method === method && op.pattern.test(path)), `${method.toUpperCase()} ${path}`).toBe(true)
      }
    }
  })

  it('智库 3 大子库的收藏联动与筛选项路径与后端 OpenAPI 完全一致', async () => {
    const libs: thinktank.ThinktankLibraryKey[] = ['knowledge', 'reports', 'proposals']
    for (const lib of libs) {
      calls.length = 0
      await thinktank.unfavoriteThinktankItem(lib, 'id-1')
      await thinktank.downloadThinktankItemBlob(lib, 'id-1')
      await filterOptions.fetchFilterOptions(`/thinktank/${lib}`)
      await filterOptions.searchFilterOptions(`/thinktank/${lib}`, 'region_tag', '北京')
      for (const { method, url } of calls) {
        const path = `/api/v1${url}`
        expect(operations.some((op) => op.method === method && op.pattern.test(path)), `${method.toUpperCase()} ${path}`).toBe(true)
      }
    }
  })

  const EXPORT_PATHS = [
    '/tender/purchaser/export',
    '/tender/winbid/export',
    '/system/users/export',
    '/codebook/area-codes/export',
    '/codebook/policy-types/export',
    '/codebook/scenarios/export',
    '/codebook/thinktank/file-types/export',
    '/codebook/thinktank/departments/export',
    '/codebook/thinktank/industries/export',
    '/codebook/thinktank/product-types/export',
    '/codebook/thinktank/provinces/export',
    '/codebook/thinktank/market-categories/export',
    '/policy/interpretations/export',
    '/policy/crawler-monitoring/sites/export',
    '/policy/crawler-config/report/export',
    '/policy/sources/export',
    '/policy/base-tags/export',
    '/thinktank/knowledge/export',
    '/thinktank/reports/export',
    '/thinktank/proposals/export',
  ]

  it.each(EXPORT_PATHS)('导出接口 GET /api/v1%s 在后端 OpenAPI 中存在', path => {
    const fullPath = `/api/v1${path}`
    expect(operations.some(op => op.method === 'get' && op.pattern.test(fullPath)), `GET ${fullPath}`).toBe(true)
  })
})
