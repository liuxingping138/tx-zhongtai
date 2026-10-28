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

/** 模板类型（政策、客户、招投标），也是授权单位：只返回当前用户能看到的类型。 */
export interface TemplateCategory {
  code: string
  name: string
  /** 能否在这个类型下新建、修改、试发、运行 */
  editable: boolean
}

/** 模板可引用的系统码表；选了就每次实时从码表服务取，不用上传的码表文件 */
export interface SystemCodeTable {
  key: string
  name: string
}

/** 模板当前生效的上线版本；定时任务和批量任务只跑它 */
export interface TemplateReleaseInfo {
  id: string
  release_no: number
  released_at: string
  released_by_name: string
  /** 上线后草稿又改了哪些会影响结果的内容，空表示和上线版本一致 */
  unreleased_changes: string[]
  title: string
  category_name: string
  content: string
  fields: string[]
  /** 上线版本引用的 Excel 列：批量任务的数据必须有这些列 */
  variables: string[]
  model_id: string
  model_name: string
  /** 码表名称（系统码表名或上传的文件名），空表示不用码表 */
  code: string
}

/** 模板最近一次样本试跑；current 表示跑的就是现在保存的草稿 */
export interface SampleSummary {
  id: string
  status: RunStatus
  total_count: number
  done_count: number
  failed_count: number
  format_failed_count: number
  created_at: string
  created_by_name: string
  current: boolean
}

/** 历史上线版本 */
export interface TemplateRelease {
  id: string
  release_no: number
  current: boolean
  title: string
  content: string
  output_fields: string
  model_id: string
  code: string
  released_at: string
  released_by_name: string
}

export interface PromptTemplate {
  id: string
  title: string
  category: string
  category_name: string
  /** 当前用户对这个模板所属类型有没有编辑权 */
  editable: boolean
  content: string
  output_fields: string
  fields: string[]
  model_id: string
  model_name: string
  excel_name: string
  excel_rows: number
  excel_headers: string[]
  code_name: string
  code_table: string
  code_table_name: string
  release: TemplateReleaseInfo | null
  sample: SampleSummary | null
  version: number
  created_at: string
  created_by_name: string
  updated_at: string
  updated_by_name: string
}

export interface PromptPayload {
  title: string
  category: string
  content: string
  output_fields: string
  model_id: string
  code_table: string
  version?: number
}

export type PromptFileKind = 'excel' | 'code'
export type RunFileKind = 'result' | 'raw' | 'log' | 'failed'
export type RunStatus = 'queued' | 'running' | 'stopping' | 'done' | 'failed' | 'cancelled' | 'interrupted'

export interface BatchRun {
  id: string
  prompt_id: string
  prompt_title: string
  prompt_category: string
  prompt_category_name: string
  /** 本次上传的数据文件名；旧任务、定时任务为空 */
  input_name: string
  /** manual：批量任务页发起；pipeline：定时任务；sample：模板页的样本试跑 */
  source: 'manual' | 'pipeline' | 'sample'
  /** 跑的是第几版上线版本；样本试跑和旧任务为空 */
  release_no: number | null
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

export function listPrompts(): Promise<{ items: PromptTemplate[]; models: AiModel[]; categories: TemplateCategory[]; code_tables: SystemCodeTable[] }> {
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

export function publishPrompt(id: string): Promise<PromptTemplate> {
  return request(http.post(`${BASE}/prompts/${id}/release`))
}

export function offlinePrompt(id: string): Promise<PromptTemplate> {
  return request(http.post(`${BASE}/prompts/${id}/offline`))
}

/** 从数据库取来的测试数据存成模板的测试 Excel（替换原来的）。 */
export function savePromptTestRows(id: string, body: { file_name: string; headers: string[]; rows: string[][] }): Promise<PromptTemplate> {
  return request(http.post(`${BASE}/prompts/${id}/test-data`, body, { timeout: 120_000 }))
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
  prompt_category?: string[]
  created_by_name?: string[]
  run_mode?: string[]
  status?: string[]
  source?: string[]
}

export function listBatchRuns(page = 1, pageSize = 15, filters: BatchRunFilters = {}): Promise<BatchRunPage> {
  return request(http.get(`${BASE}/batch-runs`, { params: { ...filters, page, page_size: pageSize } }))
}

export function batchRunFilterOptions(): Promise<{ prompt_title: string[]; created_by_name: string[] }> {
  return request(http.get(`${BASE}/batch-runs/filter-options`))
}

export function batchOptions(): Promise<{ templates: PromptTemplate[]; models: AiModel[]; categories: TemplateCategory[] }> {
  return request(http.get(`${BASE}/batch-runs/options`))
}

/** 选好数据文件后的检查结果：按哪一版、哪个模型跑多少行 */
export interface BatchInputSummary { name: string; rows: number; headers: string[]; release_no: number; model_name: string }

export function previewBatchInput(promptId: string, file: File): Promise<BatchInputSummary> {
  const form = new FormData()
  form.append('file', file)
  return request(http.post(`${BASE}/batch-runs/input-preview`, form, { params: { prompt_id: promptId }, timeout: 300_000 }))
}

/** limit 为 0 跑全部；其余参数放 query，文件放 multipart。 */
export function startBatchRun(payload: { prompt_id: string; thinking: boolean; limit: number }, file: File): Promise<BatchRun> {
  const form = new FormData()
  form.append('file', file)
  return request(http.post(`${BASE}/batch-runs`, form, { params: payload, timeout: 300_000 }))
}

export type RunRowStatus = 'done' | 'failed' | 'format' | 'pending'

/** 一行的结果：提示词用到的输入列、解析出的字段（一行可能有多条），或者失败原因 */
export interface RunRow {
  row: number
  inputs: Record<string, string>
  status: RunRowStatus
  error: string
  items: Record<string, string>[]
  /** 没设输出字段或格式不对时，模型的原话 */
  answer: string
}

export interface RunRows {
  columns: string[]
  fields: string[]
  items: RunRow[]
  /** 符合条件（如只看失败）的行数；items 最多 50 行 */
  matched: number
  total: number
}

export function getBatchRunRows(id: string, failedOnly = false): Promise<RunRows> {
  return request(http.get(`${BASE}/batch-runs/${id}/rows`, { params: { failed_only: failedOnly } }))
}

export interface SampleRunState { run: BatchRun | null; rows: RunRows | null }

export function getSampleRun(promptId: string): Promise<SampleRunState> {
  return request(http.get(`${BASE}/prompts/${promptId}/sample-run`))
}

/** 用模板上选定的模型跑，不另外传：试跑和上线后跑的是同一个模型。 */
export function startSampleRun(promptId: string, body: { thinking: boolean; limit: number }): Promise<SampleRunState> {
  return request(http.post(`${BASE}/prompts/${promptId}/sample-run`, body))
}

export function stopSampleRun(promptId: string): Promise<SampleRunState> {
  return request(http.post(`${BASE}/prompts/${promptId}/sample-run/stop`))
}

export function listPromptReleases(promptId: string): Promise<TemplateRelease[]> {
  return request(http.get(`${BASE}/prompts/${promptId}/releases`))
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
