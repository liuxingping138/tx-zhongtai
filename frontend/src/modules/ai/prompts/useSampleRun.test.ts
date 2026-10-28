import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

import type { BatchRun, PromptTemplate } from '@/api/ai'
import type { SampleRunState } from '@/api/aiSamples'

const message = vi.hoisted(() => ({ error: vi.fn() }))
const api = vi.hoisted(() => ({ getSampleRun: vi.fn(), startSampleRun: vi.fn(), stopSampleRun: vi.fn(), retrySampleRun: vi.fn() }))
const download = vi.hoisted(() => vi.fn())
vi.mock('element-plus', () => ({ ElMessage: message }))
vi.mock('@/api/aiSamples', () => api)
vi.mock('../shared/downloads', () => ({ downloadSampleFile: download }))

import { useSampleRun } from './useSampleRun'

const template = { id: 't1', title: '行业场景' } as PromptTemplate

function state(id: string, status: BatchRun['status'] = 'done', latest = id): SampleRunState {
  const brief = (no: number, runId: string) => ({ no, id: runId, status, total_count: 10, done_count: 10, failed_count: 0, format_failed_count: 0, created_at: '' })
  return { run: { id, no: 3, status } as BatchRun & { no: number }, rows: null, history: [brief(3, latest), brief(2, 'old')], compare: null }
}

function setup(current: PromptTemplate | null = template) {
  const scope = effectScope()
  const changed = vi.fn()
  const source = ref<PromptTemplate | null>(current)
  const sample = scope.run(() => useSampleRun(source, changed))!
  return { sample, changed, source, scope }
}

const settle = async () => { await Promise.resolve(); await nextTick(); await Promise.resolve() }

describe('样本试跑的数据：右栏、抽屉、试发共用一份', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    api.getSampleRun.mockResolvedValue(state('r3'))
  })
  afterEach(() => { vi.useRealTimers() })

  it('打开模板就取最近一次；模板上的「最近一次」只跟着最近一次变', async () => {
    const { sample, changed } = setup()
    await settle()
    expect(api.getSampleRun).toHaveBeenCalledWith('t1', { runId: '', compareId: '' })
    expect(sample.run.value?.id).toBe('r3')
    expect(changed).toHaveBeenCalledOnce()

    api.getSampleRun.mockResolvedValue(state('old', 'done', 'r3'))
    await sample.view('old', 'none')
    expect(api.getSampleRun).toHaveBeenLastCalledWith('t1', { runId: 'old', compareId: 'none' })
    expect(changed).toHaveBeenCalledOnce()
  })

  it('在跑时每 2 秒刷新，跑完就停', async () => {
    api.getSampleRun.mockResolvedValue(state('r3', 'running'))
    const { sample } = setup()
    await settle()
    expect(sample.running.value).toBe(true)
    api.getSampleRun.mockResolvedValue(state('r3', 'done'))
    await vi.advanceTimersByTimeAsync(2000)
    expect(api.getSampleRun).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(4000)
    expect(api.getSampleRun).toHaveBeenCalledTimes(2)
  })

  it('开始、停止、重跑失败的行都换成服务端给的结果；出错提示原因', async () => {
    const { sample } = setup()
    await settle()
    await sample.view('old', '')
    api.startSampleRun.mockResolvedValue(state('r4'))
    expect(await sample.start(5, true)).toBe(true)
    expect(api.startSampleRun).toHaveBeenCalledWith('t1', { thinking: true, limit: 5 })
    expect(sample.runId.value).toBe('')
    api.stopSampleRun.mockResolvedValue(state('r4', 'cancelled'))
    expect(await sample.stop()).toBe(true)
    api.retrySampleRun.mockRejectedValue({})
    expect(await sample.retry()).toBe(false)
    expect(api.retrySampleRun).toHaveBeenCalledWith('t1', 'r3')
    expect(message.error).toHaveBeenCalledWith('重跑没能开始，请重试')
  })

  it('下载这一次的结果，文件名带第几次', async () => {
    const { sample } = setup()
    await settle()
    await sample.download()
    expect(download).toHaveBeenCalledWith('t1', 'r3', 'result', '行业场景-第3次样本试跑结果.xlsx')
    download.mockRejectedValue({})
    await sample.download()
    expect(message.error).toHaveBeenCalledWith('下载失败，请重试')
  })

  it('没有模板时什么都不取、不发', async () => {
    const { sample } = setup(null)
    await settle()
    expect(api.getSampleRun).not.toHaveBeenCalled()
    expect(await sample.start(5, false)).toBe(false)
    expect(await sample.stop()).toBe(false)
    expect(await sample.retry()).toBe(false)
    await sample.download()
    expect(download).not.toHaveBeenCalled()
  })

  it('取结果失败时提示，安静刷新时不打扰', async () => {
    api.getSampleRun.mockRejectedValue({})
    const { sample } = setup()
    await settle()
    expect(message.error).toHaveBeenCalledWith('试跑结果加载失败，请重试')
    await sample.load(true)
    expect(message.error).toHaveBeenCalledOnce()
  })
})
