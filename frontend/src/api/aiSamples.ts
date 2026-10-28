import { AI_BASE as BASE, type BatchRun, type RunRows, type RunStatus } from './ai'
import { http, request } from './http'

/** 模板页的样本试跑和试发选行：第几次试跑、和哪一次比、测试样本的逐行数据。 */

/** 一次样本试跑的概况：按先后叫「第 no 次」 */
export interface SampleBrief {
  no: number
  id: string
  status: RunStatus
  total_count: number
  done_count: number
  failed_count: number
  format_failed_count: number
  created_at: string
}

/** 和哪一次比；测试样本换过（same_input 为 false）时没有逐行计数 */
export interface SampleCompare {
  run: SampleBrief
  same_input: boolean
  fields_changed: boolean
  fixed?: number
  broke?: number
  changed?: number
  same?: number
}

export interface SampleRunState {
  run: (BatchRun & { no: number }) | null
  rows: RunRows | null
  /** 最近 20 次，新的在前 */
  history: SampleBrief[]
  compare: SampleCompare | null
}

/** 测试样本前 100 行，每格只有开头 200 字，lengths 是整格的字数：试发选行、发之前看数据用 */
export interface TestRows {
  headers: string[]
  total: number
  rows: { row: number; values: Record<string, string>; lengths: Record<string, number> }[]
}

export function getTestRows(promptId: string): Promise<TestRows> {
  return request(http.get(`${BASE}/prompts/${promptId}/test-rows`))
}

/** 默认看最近一次、和它前一次比；compareId 为 'none' 时不比。 */
export function getSampleRun(promptId: string, options: { runId?: string; compareId?: string } = {}): Promise<SampleRunState> {
  const params = { run_id: options.runId || undefined, compare_id: options.compareId || undefined }
  return request(http.get(`${BASE}/prompts/${promptId}/sample-run`, { params }))
}

/** 只重问这次试跑里失败和没跑到的行，用的是这次冻结的提示词。 */
export function retrySampleRun(promptId: string, runId: string): Promise<SampleRunState> {
  return request(http.post(`${BASE}/prompts/${promptId}/sample-run/${runId}/retry`))
}

/** 用模板上选定的模型跑，不另外传：试跑和上线后跑的是同一个模型。 */
export function startSampleRun(promptId: string, body: { thinking: boolean; limit: number }): Promise<SampleRunState> {
  return request(http.post(`${BASE}/prompts/${promptId}/sample-run`, body))
}

export function stopSampleRun(promptId: string): Promise<SampleRunState> {
  return request(http.post(`${BASE}/prompts/${promptId}/sample-run/stop`))
}

