import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ listRuns: vi.fn<(code: string, page: number) => Promise<unknown>>() }))
vi.mock('@/api/scheduler', () => api)

import type { ScheduledJob } from '@/api/scheduler'
import { useSchedulerHistory } from './useSchedulerHistory'

const job = { code: 'crawler-v2', name: '爬虫监测增量同步' } as ScheduledJob
const pageOf = (ids: string[], total = ids.length) => ({ items: ids.map(id => ({ id })), total, page: 1, page_size: 20 })

describe('useSchedulerHistory', () => {
  beforeEach(() => api.listRuns.mockReset())

  it('打开抽屉从第一页开始加载并清空上次的记录', async () => {
    api.listRuns.mockResolvedValue(pageOf(['a', 'b'], 42))
    const history = useSchedulerHistory()
    history.page.value = 3
    history.records.value = [{ id: 'old' } as never]
    history.open(job)
    expect(history.visible.value).toBe(true)
    expect(history.records.value).toEqual([])
    await vi.waitFor(() => expect(history.loading.value).toBe(false))
    expect(api.listRuns).toHaveBeenCalledWith('crawler-v2', 1)
    expect(history.total.value).toBe(42)
    expect(history.records.value).toHaveLength(2)
  })

  it('后台轮询不显示加载状态', async () => {
    api.listRuns.mockResolvedValue(pageOf(['a']))
    const history = useSchedulerHistory()
    history.job.value = job
    const pending = history.load(true)
    expect(history.loading.value).toBe(false)
    await pending
    expect(history.records.value).toHaveLength(1)
  })

  it('先发后到的旧响应不会覆盖新结果', async () => {
    let finishFirst!: (value: unknown) => void
    api.listRuns.mockReturnValueOnce(new Promise(resolve => { finishFirst = resolve }))
    api.listRuns.mockResolvedValueOnce(pageOf(['new']))
    const history = useSchedulerHistory()
    history.job.value = job
    const first = history.load()
    await history.load()
    finishFirst(pageOf(['stale']))
    await first
    expect(history.records.value).toEqual([{ id: 'new' }])
  })

  it('加载失败显示原因，下次成功后清掉', async () => {
    api.listRuns.mockRejectedValueOnce({ status: 500, code: 'X', message: '服务繁忙' })
    const history = useSchedulerHistory()
    history.job.value = job
    await history.load()
    expect(history.error.value).toBe('服务繁忙')
    api.listRuns.mockResolvedValueOnce(pageOf([]))
    await history.load()
    expect(history.error.value).toBe('')
  })

  it('页面卸载后在途请求作废', async () => {
    let finish!: (value: unknown) => void
    api.listRuns.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const history = useSchedulerHistory()
    history.job.value = job
    const pending = history.load()
    history.stop()
    finish(pageOf(['late']))
    await pending
    expect(history.records.value).toEqual([])
  })

  it('没有选中任务时不请求', async () => {
    await useSchedulerHistory().load()
    expect(api.listRuns).not.toHaveBeenCalled()
  })
})
