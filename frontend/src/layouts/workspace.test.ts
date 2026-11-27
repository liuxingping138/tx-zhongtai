import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { ROUTE_BY_NAME } from '@/router/menu'
import { useAuthStore } from '@/stores/auth'
import { ENTRY_DESCRIPTIONS, useWorkspace } from './workspace'

// 已并入「角色与权限」、只做跳转的旧路由，不出现在菜单和查找里。
const REDIRECT_ONLY = new Set(['/system/permissions'])

describe('查找模块里的用途说明', () => {
  it('每个菜单入口都有自己的说明，不退回「进入业务模块」', () => {
    const missing = Object.values(ROUTE_BY_NAME).filter(path => !REDIRECT_ONLY.has(path) && !ENTRY_DESCRIPTIONS[path])
    expect(missing).toEqual([])
  })

  it('在线用户、登录日志和智库各模块写的是它们自己的用途', () => {
    expect(ENTRY_DESCRIPTIONS['/system/sessions']).toContain('在线')
    expect(ENTRY_DESCRIPTIONS['/system/login-logs']).toContain('登录')
    expect(ENTRY_DESCRIPTIONS['/thinktank/knowledge']).toContain('资料库')
    expect(ENTRY_DESCRIPTIONS['/thinktank/knowledge']).not.toContain('知识库')
    expect(ENTRY_DESCRIPTIONS['/thinktank/reports']).toContain('报告库')
    expect(ENTRY_DESCRIPTIONS['/thinktank/proposals']).toContain('方案库')
    expect(ENTRY_DESCRIPTIONS['/thinktank/favorites']).toContain('收藏')
    expect(ENTRY_DESCRIPTIONS['/codebook/thinktank/file-types']).toContain('文件类别')
    expect(ENTRY_DESCRIPTIONS['/codebook/thinktank/departments']).toContain('部门')
    expect(ENTRY_DESCRIPTIONS['/codebook/thinktank/industries']).toContain('行业')
    expect(ENTRY_DESCRIPTIONS['/codebook/thinktank/product-types']).toContain('产品')
    expect(ENTRY_DESCRIPTIONS['/codebook/thinktank/provinces']).toContain('省份')
    expect(ENTRY_DESCRIPTIONS['/codebook/thinktank/market-categories']).toContain('市场')
  })

  it('码表管理支持两级折叠分组，保留暂无二级的智库码表分组', () => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.menus = [
      { id: 'cb', title: '码表管理', parent_id: null, route_name: null, resource_code: null, icon: null, sort_order: 1 },
      { id: 'cb-dict', title: '数据字典', parent_id: 'cb', route_name: null, resource_code: null, icon: null, sort_order: 1 },
      { id: 'cb-pt', title: '政策类型码表', parent_id: 'cb-dict', route_name: 'codebook-policy-types', resource_code: 'codebook.policy_types', icon: null, sort_order: 1 },
      { id: 'cb-tt', title: '智库码表', parent_id: 'cb', route_name: null, resource_code: null, icon: null, sort_order: 2 },
    ]
    const { groups } = useWorkspace()
    expect(groups.value).toHaveLength(1)
    const sections = groups.value[0]!.sections!
    expect(sections.map(s => s.title)).toEqual(['数据字典', '智库码表'])
    expect(sections[0]!.entries.map(e => e.path)).toEqual(['/codebook/policy-types'])
    expect(sections[1]!.entries).toEqual([])
  })

  it('智库码表分组与智库 4 个子入口正确归组', () => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.menus = [
      { id: 'cb', title: '码表管理', parent_id: null, route_name: null, resource_code: null, icon: null, sort_order: 1 },
      { id: 'cb-tt', title: '智库码表', parent_id: 'cb', route_name: null, resource_code: null, icon: null, sort_order: 2 },
      { id: 'cb-tt-1', title: '文件类别码表', parent_id: 'cb-tt', route_name: 'codebook-thinktank-file-types', resource_code: 'codebook.thinktank_file_types', icon: null, sort_order: 521 },
      { id: 'cb-tt-2', title: '省份码表', parent_id: 'cb-tt', route_name: 'codebook-thinktank-provinces', resource_code: 'codebook.thinktank_provinces', icon: null, sort_order: 525 },
      { id: 'tt', title: '智库', parent_id: null, route_name: null, resource_code: null, icon: null, sort_order: 45 },
      { id: 'tt-k', title: '资料库', parent_id: 'tt', route_name: 'thinktank-knowledge', resource_code: 'thinktank.knowledge', icon: null, sort_order: 451 },
      { id: 'tt-r', title: '报告库', parent_id: 'tt', route_name: 'thinktank-reports', resource_code: 'thinktank.reports', icon: null, sort_order: 452 },
      { id: 'tt-p', title: '方案库', parent_id: 'tt', route_name: 'thinktank-proposals', resource_code: 'thinktank.proposals', icon: null, sort_order: 453 },
      { id: 'tt-f', title: '我的收藏', parent_id: 'tt', route_name: 'thinktank-favorites', resource_code: 'thinktank.favorites', icon: null, sort_order: 454 },
    ]
    const { groups } = useWorkspace()
    expect(groups.value).toHaveLength(2)
    expect(groups.value[0]!.sections![0]!.entries.map(e => e.path)).toEqual([
      '/codebook/thinktank/file-types',
      '/codebook/thinktank/provinces',
    ])
    expect(groups.value[1]!.entries.map(e => e.path)).toEqual([
      '/thinktank/knowledge',
      '/thinktank/reports',
      '/thinktank/proposals',
      '/thinktank/favorites',
    ])
  })
})
