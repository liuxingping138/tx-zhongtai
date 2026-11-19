import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ getCandidate: vi.fn(), getCandidateContext: vi.fn() }))
vi.mock('@/api/scenarioCandidates', () => api)

import { wasShown } from '@/api/errors'
import { useCandidateExtras } from './useCandidateExtras'

const detail = { id: 'c1', industries: [], children: [], reasons: [] }
const context = { siblings: [], similar: [], industries: [] }

describe('列表行的依据按需取', () => {
  beforeEach(() => {
    api.getCandidate.mockReset().mockResolvedValue(detail)
    api.getCandidateContext.mockReset().mockResolvedValue(context)
  })

  it('同一行展开、再点决定只取一次', async () => {
    const extras = useCandidateExtras()
    const [first, second] = await Promise.all([extras.ensure('c1'), extras.ensure('c1')])
    await extras.ensure('c1')
    expect(first).toBe(second)
    expect(first.detail).toEqual(detail)
    expect(extras.get('c1')?.loading).toBe(false)
    expect(api.getCandidate).toHaveBeenCalledOnce()
  })

  it('码表取不到照样有详情，只是写明码表那块看不了', async () => {
    const err = new Error('down')
    api.getCandidateContext.mockRejectedValue(err)
    const found = await useCandidateExtras().ensure('c1')
    expect(found.detail).toEqual(detail)
    expect(found.context).toBeNull()
    expect(found.contextError).toBeTruthy()
    expect(wasShown(err)).toBe(true)
  })

  it('任一请求刚失败就立即 markShown，避免慢请求拖过零延迟触发全局重复提示', async () => {
    const fastErr = new Error('fast fail')
    api.getCandidate.mockRejectedValueOnce(fastErr)
    let resolveSlow!: (v: typeof context) => void
    api.getCandidateContext.mockReturnValueOnce(new Promise(resolve => { resolveSlow = resolve }))
    const pending = useCandidateExtras().ensure('c1')
    await Promise.resolve()
    await Promise.resolve()
    expect(wasShown(fastErr)).toBe(true)
    resolveSlow(context)
    await pending
  })

  it('详情没取到的下次重取；做完决定 drop 后也重取', async () => {
    api.getCandidate.mockRejectedValueOnce(new Error('down'))
    const extras = useCandidateExtras()
    expect((await extras.ensure('c1')).detail).toBeNull()
    expect((await extras.ensure('c1')).detail).toEqual(detail)
    extras.drop('c1')
    expect(extras.get('c1')).toBeUndefined()
    await extras.ensure('c1')
    expect(api.getCandidate).toHaveBeenCalledTimes(3)
  })
})
