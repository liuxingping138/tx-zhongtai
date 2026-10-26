import { describe, expect, it } from 'vitest'

import { SCHEDULER_SERVICES } from './scheduler'
import { mergeOverviews } from './schedulerOverview'

const job = (code: string) => ({
  code, name: code, enabled: true, daily_time: '03:30', next_run_at: null, version: 1,
  watermark: null, active_run: null, last_run: null,
})
const ok = (codes: string[], online = true) => ({
  status: 'fulfilled' as const,
  value: { items: codes.map(job), timezone: 'Asia/Shanghai', worker_online: online, heartbeat_at: online ? '2026-10-26T03:00:00Z' : null },
})
const down = { status: 'rejected' as const, reason: new Error('503') }
const describeError = () => '服务暂不可用'

describe('调度页汇总各服务的任务', () => {
  it('按服务顺序合并，每个任务带上所属服务的接口前缀', () => {
    const overview = mergeOverviews(SCHEDULER_SERVICES, [ok(['crawler', 'crawler_config']), ok(['iam_session_cleanup'])], describeError)
    expect(overview.items.map(item => [item.code, item.base])).toEqual([
      ['crawler', SCHEDULER_SERVICES[0].base],
      ['crawler_config', SCHEDULER_SERVICES[0].base],
      ['iam_session_cleanup', SCHEDULER_SERVICES[1].base],
    ])
    expect(overview.workers.every(worker => worker.online)).toBe(true)
  })

  it('一个服务取不到或执行进程离线时点名，其他服务的任务照常显示', () => {
    const overview = mergeOverviews(SCHEDULER_SERVICES, [ok(['crawler'], false), down], describeError)
    expect(overview.items.map(item => item.code)).toEqual(['crawler'])
    expect(overview.workers).toEqual([
      { service: '政策服务', online: false, heartbeat_at: null, error: '' },
      { service: '系统管理', online: false, heartbeat_at: null, error: '服务暂不可用' },
    ])
  })

  it('全都取不到才算加载失败', () => {
    expect(() => mergeOverviews(SCHEDULER_SERVICES, [down, down], describeError)).toThrow('503')
  })
})
