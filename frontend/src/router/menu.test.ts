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
function flatten(records: RouteRecordRaw[], parent = ''): { name: string; path: string }[] {
  const out: { name: string; path: string }[] = []
  for (const record of records) {
    const path = record.path.startsWith('/')
      ? record.path
      : `${parent.replace(/\/$/, '')}/${record.path}`.replace(/\/$/, '') || '/'
    if (record.name) out.push({ name: String(record.name), path })
    if (record.children) out.push(...flatten(record.children, path))
  }
  return out
}

const MODULE_PREFIXES = ['/system/', '/codebook/', '/policy/', '/ai/']

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
})
