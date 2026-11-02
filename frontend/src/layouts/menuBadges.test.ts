import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive, type EffectScope } from 'vue'

const route = reactive({ fullPath: '/policy/sources', path: '/policy/sources' })
const api = vi.hoisted(() => ({ candidatePendingCount: vi.fn() }))
const auth = vi.hoisted(() => ({ canRead: vi.fn(() => true) }))
vi.mock('vue-router', () => ({ useRoute: () => route }))
vi.mock('@/api/scenarioCandidates', () => api)
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))

import { useMenuBadges } from './menuBadges'

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

  it('在审核页里换到下一个时强制刷新', async () => {
    setup()
    await flush()
    Object.assign(route, { fullPath: '/policy/scenario-candidates/c2?pos=0', path: '/policy/scenario-candidates/c2' })
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
