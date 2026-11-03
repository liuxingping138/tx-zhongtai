import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive, type EffectScope } from 'vue'

const route = reactive({ fullPath: '/policy/sources', path: '/policy/sources' })
const api = vi.hoisted(() => ({ candidatePendingCount: vi.fn() }))
const auth = vi.hoisted(() => ({ canRead: vi.fn(() => true) }))
vi.mock('vue-router', () => ({ useRoute: () => route }))
vi.mock('@/api/scenarioCandidates', () => api)
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))

import { refreshMenuBadges, useMenuBadges } from './menuBadges'

const flush = () => new Promise(resolve => setTimeout(resolve, 0))
let scope: EffectScope
function setup() {
  scope = effectScope()
  return scope.run(() => useMenuBadges())!
}
afterEach(() => scope.stop())

describe('侧栏待审数', () => {
  beforeEach(() => {
    api.candidatePendingCount.mockReset().mockResolvedValue({ pending: 4 })
    auth.canRead.mockReturnValue(true)
    Object.assign(route, { fullPath: '/policy/sources', path: '/policy/sources' })
  })

  it('有查看权限才取数，别处换页一分钟内不重复取', async () => {
    const { counts } = setup()
    await flush()
    expect(counts.value['/policy/scenario-candidates']).toBe(4)
    route.fullPath = '/policy/base-tags'
    await nextTick()
    await flush()
    expect(api.candidatePendingCount).toHaveBeenCalledOnce()
  })

  it('在新增场景审核里换页签时强制刷新', async () => {
    setup()
    await flush()
    Object.assign(route, { fullPath: '/policy/scenario-candidates?status=已驳回', path: '/policy/scenario-candidates' })
    await nextTick()
    await flush()
    expect(api.candidatePendingCount).toHaveBeenCalledTimes(2)
  })

  it('列表行上做完决定（地址不变）时也马上刷新', async () => {
    setup()
    await flush()
    refreshMenuBadges()
    await nextTick()
    await flush()
    expect(api.candidatePendingCount).toHaveBeenCalledTimes(2)
  })

  it('没有查看权限不取', async () => {
    auth.canRead.mockReturnValue(false)
    const { counts } = setup()
    await flush()
    expect(api.candidatePendingCount).not.toHaveBeenCalled()
    expect(counts.value).toEqual({})
  })
})
