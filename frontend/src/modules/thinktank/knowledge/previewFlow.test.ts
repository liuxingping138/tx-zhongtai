import { describe, expect, it, vi } from 'vitest'
import { openRecord } from './previewFlow'

describe('openRecord', () => {
  it('资料信息一到就渲染并结束，不等原文（转码中的 PPT 不挡整页）', async () => {
    const onMeta = vi.fn()
    const never = new Promise<unknown>(() => {})
    const startContent = vi.fn(() => never)

    const done = await openRecord({ fetchMeta: () => Promise.resolve('meta'), isCurrent: () => true, onMeta, startContent })

    expect(done).toBe(true)
    expect(onMeta).toHaveBeenCalledWith('meta')
    expect(startContent).toHaveBeenCalledOnce()
  })

  it('等资料信息期间换了记录：不渲染、不取原文', async () => {
    const onMeta = vi.fn()
    const startContent = vi.fn(() => Promise.resolve())
    const done = await openRecord({ fetchMeta: () => Promise.resolve('old'), isCurrent: () => false, onMeta, startContent })
    expect(done).toBe(false)
    expect(onMeta).not.toHaveBeenCalled()
    expect(startContent).not.toHaveBeenCalled()
  })

  it('资料信息取失败照常抛给页面显示错误', async () => {
    await expect(openRecord({
      fetchMeta: () => Promise.reject(new Error('404')),
      isCurrent: () => true,
      onMeta: vi.fn(),
      startContent: vi.fn(),
    })).rejects.toThrow('404')
  })
})
