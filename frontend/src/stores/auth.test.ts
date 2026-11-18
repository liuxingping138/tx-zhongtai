import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  changePassword: vi.fn(),
  fetchMe: vi.fn(),
  fetchPermissions: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  logoutAll: vi.fn(),
}))
const session = vi.hoisted(() => ({
  token: '',
  armAccessRefresh: vi.fn(),
  broadcastLogout: vi.fn(),
  disarmAccessRefresh: vi.fn(),
  ensureCsrfToken: vi.fn(),
  getAccessToken: vi.fn(),
  refreshSession: vi.fn(),
  setAccessToken: vi.fn(),
  setCsrfToken: vi.fn(),
}))
vi.mock('@/api/auth', () => api)
vi.mock('@/api/session', () => session)

import type { MenuItem } from '@/api/types'
import { useAuthStore } from './auth'

const me = (overrides = {}) => ({ id: 'u1', username: 'zs', display_name: '张三', must_change_password: false, is_superadmin: false, ...overrides })
const menu = (id: string, parent: string | null, route: string | null): MenuItem => ({
  id, parent_id: parent, title: id, route_name: route, resource_code: null, icon: null, sort_order: 1,
})

beforeEach(() => {
  setActivePinia(createPinia())
  Object.values(api).forEach(fn => fn.mockReset())
  session.token = ''
  Object.values(session).forEach(fn => typeof fn === 'function' && fn.mockReset())
  session.getAccessToken.mockImplementation(() => session.token)
  session.setAccessToken.mockImplementation((token: string) => { session.token = token })
  session.ensureCsrfToken.mockResolvedValue('csrf')
  api.fetchMe.mockResolvedValue(me())
  api.fetchPermissions.mockResolvedValue({ resources: [{ code: 'policy.sources', level: 'EXPORT' }], menus: [] })
})

describe('权限判断', () => {
  it('档位逐级包含：导出档能看能导，但不能管理', () => {
    const store = useAuthStore()
    store.resources = [{ code: 'policy.sources', level: 'EXPORT' }, { code: 'system.users', level: 'FULL' }] as never
    expect(store.canRead('policy.sources')).toBe(true)
    expect(store.canExport('policy.sources')).toBe(true)
    expect(store.canFull('policy.sources')).toBe(false)
    expect(store.canFull('system.users')).toBe(true)
    expect(store.resourceLevel('policy.sources')).toBe('EXPORT')
  })

  it('没有授权记录就什么都不能做', () => {
    const store = useAuthStore()
    expect(store.canRead('x')).toBe(false)
    expect(store.canExport('x')).toBe(false)
    expect(store.canFull('x')).toBe(false)
    expect(store.resourceLevel('x')).toBeNull()
  })

  it('超级管理员标记取自个人信息', () => {
    const store = useAuthStore()
    expect(store.isSuperadmin).toBe(false)
    store.user = me({ is_superadmin: true }) as never
    expect(store.isSuperadmin).toBe(true)
  })

  it('没有任何可进入页面的目录不显示', () => {
    const store = useAuthStore()
    store.menus = [
      menu('policy', null, null),
      menu('sources', 'policy', 'policy-sources'),
      menu('empty-dir', null, null),
      menu('nested', null, null),
      menu('nested-child', 'nested', null),
      menu('nested-leaf', 'nested-child', 'x'),
    ]
    expect(store.visibleMenus.map(item => item.id)).toEqual(['policy', 'sources', 'nested', 'nested-child', 'nested-leaf'])
  })

  it('已登录还要有访问令牌才算认证通过', () => {
    const withoutToken = useAuthStore()
    withoutToken.signedIn = true
    expect(withoutToken.isAuthenticated).toBe(false)
    setActivePinia(createPinia())
    session.token = 't'
    const withToken = useAuthStore()
    withToken.signedIn = true
    expect(withToken.isAuthenticated).toBe(true)
  })
})

describe('bootstrap', () => {
  it('没有令牌时先用刷新凭据换一个，再加载个人信息与权限', async () => {
    session.refreshSession.mockImplementation(() => {
      session.token = 'fresh'
      return Promise.resolve({ must_change_password: false })
    })
    const store = useAuthStore()
    await store.bootstrap()
    expect(store.signedIn).toBe(true)
    expect(store.user?.username).toBe('zs')
    expect(store.canExport('policy.sources')).toBe(true)
    expect(store.bootstrapped).toBe(true)
  })

  it('刷新凭据失效时清空身份，仍然标记为已启动，页面据此跳登录', async () => {
    session.refreshSession.mockRejectedValue({ response: { status: 401 } })
    const store = useAuthStore()
    store.user = me() as never
    await store.bootstrap()
    expect(store.user).toBeNull()
    expect(store.bootstrapped).toBe(true)
    expect(store.signedIn).toBe(false)
    expect(session.setAccessToken).toHaveBeenCalledWith('')
  })

  it('服务暂时不可用（部署时 IAM 重启、网关 502）时不清身份，下次进页面再试', async () => {
    session.refreshSession.mockRejectedValue({ response: { status: 503 } })
    const store = useAuthStore()
    await store.bootstrap()
    expect([store.unavailable, store.bootstrapped]).toEqual([true, false])
    expect(session.setAccessToken).not.toHaveBeenCalled()
    session.token = 't'
    await store.bootstrap()
    expect([store.unavailable, store.bootstrapped, store.signedIn]).toEqual([false, true, true])
  })

  it('取个人信息被拒（续期也失败）同样按会话失效处理', async () => {
    session.token = 't'
    api.fetchMe.mockRejectedValue({ status: 401 })
    const store = useAuthStore()
    await store.bootstrap()
    expect([store.signedIn, store.bootstrapped]).toEqual([false, true])
  })

  it('只启动一次', async () => {
    session.token = 't'
    const store = useAuthStore()
    await store.bootstrap()
    await store.bootstrap()
    expect(api.fetchMe).toHaveBeenCalledOnce()
  })
})

describe('登录与改密', () => {
  it('登录后保存令牌、安排续期、加载权限', async () => {
    api.login.mockResolvedValue({ access_token: 'tok', expires_in: 900, must_change_password: false })
    const store = useAuthStore()
    await store.signIn('zs', 'pw')
    expect(session.armAccessRefresh).toHaveBeenCalledWith(900)
    expect(store.signedIn).toBe(true)
    expect(store.resources).toHaveLength(1)
  })

  it('首次登录必须改密时不加载任何权限和菜单', async () => {
    api.login.mockResolvedValue({ access_token: 'tok', expires_in: 900, must_change_password: true })
    api.fetchMe.mockResolvedValue(me({ must_change_password: true }))
    const store = useAuthStore()
    await store.signIn('zs', 'pw')
    expect(store.mustChangePassword).toBe(true)
    expect(store.resources).toEqual([])
    expect(api.fetchPermissions).not.toHaveBeenCalled()
  })

  it('改密成功后换新令牌并解除强制改密', async () => {
    api.changePassword.mockResolvedValue({ access_token: 'new', expires_in: 900, must_change_password: false })
    const store = useAuthStore()
    store.mustChangePassword = true
    await store.updatePassword('old', 'new')
    expect(store.mustChangePassword).toBe(false)
    expect(api.fetchPermissions).toHaveBeenCalled()
  })
})

describe('退出', () => {
  it('服务端退出失败也照常清理本地并通知其他标签页', async () => {
    api.logout.mockRejectedValue(new Error('offline'))
    const store = useAuthStore()
    store.signedIn = true
    store.user = me() as never
    await store.signOut()
    expect(store.signedIn).toBe(false)
    expect(store.user).toBeNull()
    expect(session.broadcastLogout).toHaveBeenCalledOnce()
    expect(session.disarmAccessRefresh).toHaveBeenCalled()
  })

  it('退出全部设备返回撤销的会话数', async () => {
    api.logoutAll.mockResolvedValue({ revoked: 3 })
    const store = useAuthStore()
    expect(await store.signOutAll()).toBe(3)
    expect(session.setCsrfToken).toHaveBeenCalledWith('')
  })

  it('顶级无叶模块隐藏，但同一模块下的空子级目录（如智库码表）保留可见', () => {
    const store = useAuthStore()
    store.menus = [
      { id: 'empty-root', title: '空模块', parent_id: null, route_name: null, resource_code: null, icon: null, sort_order: 1 },
      { id: 'cb', title: '码表管理', parent_id: null, route_name: null, resource_code: null, icon: null, sort_order: 2 },
      { id: 'cb-dict', title: '数据字典', parent_id: 'cb', route_name: null, resource_code: null, icon: null, sort_order: 1 },
      { id: 'cb-pt', title: '政策类型码表', parent_id: 'cb-dict', route_name: 'codebook-policy-types', resource_code: 'codebook.policy_types', icon: null, sort_order: 1 },
      { id: 'cb-tt', title: '智库码表', parent_id: 'cb', route_name: null, resource_code: null, icon: null, sort_order: 2 },
    ]
    const ids = store.visibleMenus.map(m => m.id)
    expect(ids).not.toContain('empty-root')
    expect(ids).toEqual(['cb', 'cb-dict', 'cb-pt', 'cb-tt'])
  })
})
