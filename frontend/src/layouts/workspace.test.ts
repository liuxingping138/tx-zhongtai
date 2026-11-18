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

  it('在线用户、登录日志写的是它们自己的用途', () => {
    expect(ENTRY_DESCRIPTIONS['/system/sessions']).toContain('在线')
    expect(ENTRY_DESCRIPTIONS['/system/login-logs']).toContain('登录')
    expect(ENTRY_DESCRIPTIONS['/thinktank/knowledge']).toContain('知识库')
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
    expect(groups.value[0]?.sections?.map(s => s.title)).toEqual(['数据字典', '智库码表'])
    expect(groups.value[0]?.sections?.[0]?.entries.map(e => e.path)).toEqual(['/codebook/policy-types'])
    expect(groups.value[0]?.sections?.[1]?.entries).toEqual([])
  })
})
