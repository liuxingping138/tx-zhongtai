import type { RouteRecordRaw } from 'vue-router'
import { describe, expect, it } from 'vitest'

import { routes } from './routes'
import { ROUTE_BY_NAME, pathForRouteName } from './menu'

/**
 * 顶部导航和侧栏都靠 ROUTE_BY_NAME 把后端菜单的 route_name 翻成前端路径，
 * 查不到就把该菜单静默过滤掉。新增模块只改 router/index.ts 而漏了这张表时，
 * 页面能直接用 URL 打开、菜单却永远不出现，而且不报任何错——必须由测试兜住。
 *
 * 这里不导入 router 实例：createWebHistory() 需要 window，单测跑在 node 环境。
 */
function flatten(records: RouteRecordRaw[], parent = ''): { name: string; path: string; meta?: RouteRecordRaw['meta'] }[] {
  const out: { name: string; path: string; meta?: RouteRecordRaw['meta'] }[] = []
  for (const record of records) {
    const path = record.path.startsWith('/')
      ? record.path
      : `${parent.replace(/\/$/, '')}/${record.path}`.replace(/\/$/, '') || '/'
    if (record.name) out.push({ name: String(record.name), path, meta: record.meta })
    if (record.children) out.push(...flatten(record.children, path))
  }
  return out
}

const MODULE_PREFIXES = ['/system/', '/codebook/', '/policy/', '/thinktank/', '/ai/']

const all = flatten(routes)
// 带路径参数的是详情/子页（如角色授权），不进菜单，不参与映射校验。
const moduleRoutes = all.filter(
  (route) => !route.path.includes(':') && MODULE_PREFIXES.some((prefix) => route.path.startsWith(prefix)),
)

describe('ROUTE_BY_NAME 与路由表', () => {
  it('每个业务模块页都在菜单映射里', () => {
    const missing = moduleRoutes.map((route) => route.name).filter((name) => !(name in ROUTE_BY_NAME))
    expect(missing, `这些路由缺少 ROUTE_BY_NAME 映射，菜单里不会出现：${missing.join(', ')}`).toEqual([])
  })

  it('映射到的路径与路由表实际路径一致', () => {
    for (const route of moduleRoutes) {
      expect(pathForRouteName(route.name), `${route.name} 的映射路径与路由表不一致`).toBe(route.path)
    }
  })

  it('映射表里没有指向不存在路由的残留项', () => {
    const known = new Set(all.map((route) => route.name))
    const stale = Object.keys(ROUTE_BY_NAME).filter((name) => !known.has(name))
    expect(stale, `这些映射指向已不存在的路由：${stale.join(', ')}`).toEqual([])
  })

  it('智库 6 张码表路由元信息完整', () => {
    const byName = new Map(all.map((route) => [route.name, route]))
    const dictSpecs = [
      ['codebook-thinktank-file-types', 'file-types', 'codebook.thinktank_file_types'],
      ['codebook-thinktank-departments', 'departments', 'codebook.thinktank_departments'],
      ['codebook-thinktank-industries', 'industries', 'codebook.thinktank_industries'],
      ['codebook-thinktank-product-types', 'product-types', 'codebook.thinktank_product_types'],
      ['codebook-thinktank-provinces', 'provinces', 'codebook.thinktank_provinces'],
      ['codebook-thinktank-market-categories', 'market-categories', 'codebook.thinktank_market_categories'],
    ] as const
    for (const [name, slug, resource] of dictSpecs) {
      expect(byName.get(name)!.meta).toMatchObject({ dictSlug: slug, resource })
    }
  })

  it('智库资料库、报告库、方案库与我的收藏路由元信息完整', () => {
    const byName = new Map(all.map((route) => [route.name, route]))
    expect(byName.get('thinktank-knowledge')!.meta).toMatchObject({ title: '资料库', resource: 'thinktank.knowledge' })
    expect(byName.get('thinktank-knowledge-preview')!.meta).toMatchObject({
      title: '资料库文件预览',
      menuPath: '/thinktank/knowledge',
    })
    expect(byName.get('thinktank-report-preview')!.meta).toMatchObject({
      title: '报告库文件预览',
      resource: 'thinktank.reports',
      menuPath: '/thinktank/reports',
    })
    expect(byName.get('thinktank-proposal-preview')!.meta).toMatchObject({
      title: '方案库文件预览',
      resource: 'thinktank.proposals',
      menuPath: '/thinktank/proposals',
    })
    expect(byName.get('thinktank-favorites')!.meta).toMatchObject({
      title: '我的收藏',
      resource: 'thinktank.favorites',
    })
  })
})
