import { http, request } from './http'

export interface AiModel {
  id: string
  name: string
  provider: string
  web_search: boolean
  supports_thinking: boolean
  /** 服务端配了这家厂商的密钥才可用 */
  available: boolean
  input_price: string
  output_price: string
  search_price: string
}

export interface PromptTemplate {
  id: string
  title: string
  content: string
  output_fields: string
  fields: string[]
  model_id: string
  model_name: string
  excel_name: string
  excel_rows: number
  excel_headers: string[]
  code_name: string
  version: number
  created_at: string
  created_by_name: string
  updated_at: string
  updated_by_name: string
}

export interface PromptPayload {
  title: string
  content: string
  output_fields: string
  model_id: string
  version?: number
}

export type PromptFileKind = 'excel' | 'code'
export type RunFileKind = 'result' | 'raw' | 'log' | 'failed'
export type RunStatus = 'queued' | 'running' | 'stopping' | 'done' | 'failed' | 'cancelled' | 'interrupted'

export interface BatchRun {
  id: string
  prompt_id: string
  prompt_title: string
  prompt_content: string
  output_fields: string
  model_id: string
  model_name: string
  thinking: boolean
  row_limit: number
  /** test：运行 N 条测试；all：运行全部 */
  run_mode: 'test' | 'all'
  status: RunStatus
  total_count: number
  done_count: number
  failed_count: number
  /** 失败里「模型回答了但解析不出输出字段」的条数 */
  format_failed_count: number
  /** 重跑时要问的行：失败的 + 没跑到的 */
  pending_count: number
  can_retry: boolean
  percent: number
  total_tokens_kilo: number
  inference_cost: number
  search_cost: number
  search_calls: number
  error_message: string
  cancel_requested: boolean
  can_stop: boolean
  can_delete: boolean
  files: Record<RunFileKind, boolean>
  created_at: string
  created_by_name: string
  started_at: string
  finished_at: string
}

export interface BatchRunPage {
  items: BatchRun[]
  total: number
  page: number
  page_size: number
}

export const AI_BASE = '/ai'
const BASE = AI_BASE

export function listPrompts(): Promise<{ items: PromptTemplate[]; models: AiModel[] }> {
  return request(http.get(`${BASE}/prompts`))
}

export function createPrompt(payload: PromptPayload): Promise<PromptTemplate> {
  return request(http.post(`${BASE}/prompts`, payload))
}

export function updatePrompt(id: string, payload: PromptPayload): Promise<PromptTemplate> {
  return request(http.put(`${BASE}/prompts/${id}`, payload))
}

export function deletePrompt(id: string): Promise<null> {
  return request(http.delete(`${BASE}/prompts/${id}`))
}

export function uploadPromptFile(id: string, kind: PromptFileKind, file: File): Promise<PromptTemplate> {
  const form = new FormData()
  form.append('file', file)
  return request(http.post(`${BASE}/prompts/${id}/files/${kind}`, form, { timeout: 300_000 }))
}

export function deletePromptFile(id: string, kind: PromptFileKind): Promise<PromptTemplate> {
  return request(http.delete(`${BASE}/prompts/${id}/files/${kind}`))
}

export interface BatchRunFilters {
  prompt_title?: string[]
  created_by_name?: string[]
  run_mode?: string[]
  status?: string[]
}

export function listBatchRuns(page = 1, pageSize = 15, filters: BatchRunFilters = {}): Promise<BatchRunPage> {
  return request(http.get(`${BASE}/batch-runs`, { params: { ...filters, page, page_size: pageSize } }))
}

export function batchRunFilterOptions(): Promise<{ prompt_title: string[]; created_by_name: string[] }> {
  return request(http.get(`${BASE}/batch-runs/filter-options`))
}

export function batchOptions(): Promise<{ templates: PromptTemplate[]; models: AiModel[] }> {
  return request(http.get(`${BASE}/batch-runs/options`))
}

export function startBatchRun(payload: { prompt_id: string; model_id: string; thinking: boolean; limit: number }): Promise<BatchRun> {
  return request(http.post(`${BASE}/batch-runs`, payload))
}

export function getBatchRun(id: string): Promise<BatchRun> {
  return request(http.get(`${BASE}/batch-runs/${id}`))
}

/** 重跑失败和没跑到的行，已成功的沿用，结果合并回原任务。 */
export function retryBatchRun(id: string): Promise<BatchRun> {
  return request(http.post(`${BASE}/batch-runs/${id}/retry`))
}

export function stopBatchRun(id: string): Promise<BatchRun> {
  return request(http.post(`${BASE}/batch-runs/${id}/stop`))
}

export function deleteBatchRun(id: string): Promise<null> {
  return request(http.delete(`${BASE}/batch-runs/${id}`))
}

export function chatModels(): Promise<AiModel[]> {
  return request(http.get(`${BASE}/chat/models`))
}

/** 「模型配置」页的一行。单价是文本，没配的档位为空串；枚举字段是代码值，页面显示前换成中文。 */
export interface ModelConfig {
  id: string
  name: string
  provider: string
  provider_name: string
  endpoint: string
  web_search: boolean
  thinking: string
  reasoning_effort: string
  service_tier: string
  input_price: string
  output_price: string
  flex_input_price: string
  flex_output_price: string
  peak_input_price: string
  peak_output_price: string
  peak_hours: string
  search_price: string
  rate_limit: string
  enabled: boolean
  sort_order: number
  version: number
  created_at: string
  created_by_name: string
  updated_at: string
  updated_by_name: string
}

export type ModelConfigBody = Omit<ModelConfig, 'provider_name' | 'version' | 'created_at' | 'created_by_name' | 'updated_at' | 'updated_by_name'>

export function listModelConfigs(): Promise<ModelConfig[]> {
  return request(http.get(`${BASE}/models`))
}

export function createModelConfig(body: ModelConfigBody): Promise<ModelConfig> {
  return request(http.post(`${BASE}/models`, body))
}

export function updateModelConfig(id: string, body: ModelConfigBody & { version: number }): Promise<ModelConfig> {
  return request(http.put(`${BASE}/models/${encodeURIComponent(id)}`, body))
}
