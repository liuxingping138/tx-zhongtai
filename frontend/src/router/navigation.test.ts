import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { MenuItem } from '@/api/types'

const auth = vi.hoisted(() => ({
  bootstrapped: true,
  isAuthenticated: true,
  mustChangePassword: false,
  resources: [] as unknown[],
  visibleMenus: [] as MenuItem[],
  bootstrap: vi.fn(),
  canRead: vi.fn(() => true),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('vue-router', async importOriginal => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return { ...actual, createWebHistory: actual.createMemoryHistory }
})

import router from './index'

function menu(id: string, route_name: string | null, parent_id: string | null = null): MenuItem {
  return { id, route_name, parent_id, title: id, resource_code: null, icon: null, sort_order: 0 }
}

beforeEach(async () => {
  vi.stubGlobal('document', { title: '' })
  auth.bootstrapped = true
  auth.isAuthenticated = false
  auth.mustChangePassword = false
  auth.visibleMenus = []
  auth.resources = []
  auth.canRead.mockReturnValue(true)
  await router.push('/login')
  auth.isAuthenticated = true
})

describe('正式导航入口和原权限门禁', () => {
  it('只有码表权限时进入码表，不硬编码跳政策页', async () => {
    auth.visibleMenus = [menu('码表管理', null), menu('政策类型', 'codebook-policy-types', '码表管理')]
    await router.push('/')
    expect(router.currentRoute.value.path).toBe('/codebook/policy-types')
  })

  it('没有已发布可用菜单时进入空权限页', async () => {
    auth.visibleMenus = [menu('尚未接入的菜单', 'unknown-route')]
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('no-modules')
  })

  it('根地址进入菜单顺序的首个模块，与顶部导航一致', async () => {
    auth.visibleMenus = [menu('系统管理', null), menu('用户管理', 'system-users', '系统管理'), menu('政策', null), menu('信源', 'policy-sources', '政策')]
    await router.push('/')
    expect(router.currentRoute.value.path).toBe('/system/users')
  })

  it('没有系统管理权限时，根地址进入首个业务模块', async () => {
    auth.visibleMenus = [menu('政策', null), menu('信源', 'policy-sources', '政策'), menu('码表管理', null), menu('政策类型', 'codebook-policy-types', '码表管理')]
    await router.push('/')
    expect(router.currentRoute.value.path).toBe('/policy/sources')
  })

  it('清理预览参数但保留业务筛选与锚点', async () => {
    await router.push('/policy/sources?design-preview=1&province=北京#filters')
    expect(router.currentRoute.value.query).toEqual({ province: '北京' })
    expect(router.currentRoute.value.hash).toBe('#filters')
  })

  it('必须修改密码的账号仍先进入改密页', async () => {
    auth.mustChangePassword = true
    auth.visibleMenus = [menu('信源', 'policy-sources')]
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('change-password')
  })

  it('未登录访问业务页仍进入登录并保留返回地址', async () => {
    auth.isAuthenticated = false
    await router.push('/policy/sources')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/policy/sources')
  })

  it('隐藏导航不代替权限守卫，直达无权地址仍拒绝', async () => {
    auth.canRead.mockReturnValue(false)
    await router.push('/system/users')
    expect(router.currentRoute.value.name).toBe('forbidden')
  })
})
