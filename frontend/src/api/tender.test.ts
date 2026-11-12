import { describe, expect, it, vi } from 'vitest'
import {
  getTenderContent,
  getTenderCount,
  getTenderRecord,
  getTenderStatistics,
  getTenderTotals,
  listTenderRecords,
} from './tender'

vi.mock('./http', () => ({
  http: {
    get: vi.fn((url: string, config?: Record<string, unknown>) => Promise.resolve({ data: { data: { url, config } } })),
  },
  request: vi.fn((promise: Promise<{ data: { data: unknown } }>) => promise.then(res => res.data.data)),
}))

describe('tender api module', () => {
  it('listTenderRecords cleans empty and null params', async () => {
    const res = (await listTenderRecords('purchaser', {
      project_name: '测试项目',
      empty_str: '',
      null_val: null,
      page: 1,
    })) as unknown as { config: { params: Record<string, unknown>; timeout: number } }

    expect(res.config.params).toEqual({
      project_name: '测试项目',
      page: 1,
    })
    expect(res.config.timeout).toBe(60_000)
  })

  it('getTenderRecord requests correct endpoint with project_status query', async () => {
    const res = (await getTenderRecord('winbid', '12345', '1')) as unknown as {
      url: string
      config: { params: { project_status: string } }
    }
    expect(res.url).toBe('/tender/winbid/12345')
    expect(res.config.params.project_status).toBe('1')
  })

  it('getTenderContent requests content endpoint with project_status', async () => {
    const res = (await getTenderContent('purchaser', '999', '0')) as unknown as {
      url: string
      config: { params: { project_status: string } }
    }
    expect(res.url).toBe('/tender/purchaser/999/content')
    expect(res.config.params.project_status).toBe('0')
  })

  it('getTenderStatistics passes dates and sets 120s timeout', async () => {
    const res = (await getTenderStatistics('2026-11-01', '2026-11-12')) as unknown as {
      url: string
      config: { params: Record<string, string>; timeout: number }
    }
    expect(res.url).toBe('/tender/statistics')
    expect(res.config.params).toEqual({
      date_from: '2026-11-01',
      date_to: '2026-11-12',
    })
    expect(res.config.timeout).toBe(120_000)
  })

  it('getTenderTotals calls totals endpoint with 60s timeout', async () => {
    const res = (await getTenderTotals()) as unknown as {
      url: string
      config: { timeout: number }
    }
    expect(res.url).toBe('/tender/statistics/totals')
    expect(res.config.timeout).toBe(60_000)
  })

  it('getTenderCount cleans empty params', async () => {
    const res = (await getTenderCount('winbid', {
      project_status: '1',
      blank: '',
    })) as unknown as {
      url: string
      config: { params: Record<string, unknown> }
    }
    expect(res.url).toBe('/tender/winbid/count')
    expect(res.config.params).toEqual({ project_status: '1' })
  })
})
