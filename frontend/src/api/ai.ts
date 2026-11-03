import { http, request } from './http'

export interface AiModel {
  id: string
  name: string
  provider: string
  web_search: boolean
  supports_thinking: boolean
  /** 服务端配了这家厂商的密钥才可用 */
  available: boolean
  /** 此刻适用的单价（每千 token）：低优档、分时计价的模型会随时段变 */
  input_price: string
  output_price: string
  search_price: string
  /** 上面的价是哪一档：低优档、高峰价（工作日几点到几点）、平时价，单一价为空 */
  price_note: string
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
  /** 这次试跑一共花了多少（元），新建批量任务按它估每条的费用 */
  cost: number
  /** 试跑时开没开深度思考：和要跑的任务不一样就不拿它估费用 */
  thinking: boolean
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
  /** 跑的是第几版上线版本；跑草稿、样本试跑和旧任务为空 */
  release_no: number | null
  /** 跑的是哪次保存的草稿（批量任务可以不等上线；样本试跑也记）；跑上线版本时为空串 */
  draft_saved_at: string
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
  /** 自动重跑到了第几轮（一次执行最多三轮，样本试跑只跑一轮）、这一轮重问几条、等待中的话几点开始 */
  retry_round: number
  round_rows: number
  round_starts_at: string
  can_retry: boolean
  /** 页面发起、只跑了前几行、已结束：可以用同一份数据跑全部 */
  can_run_all: boolean
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
  /** 执行进程（ai-worker）最近一分钟有没有心跳；不在时排队的任务不会开始。 */
  worker_online: boolean
}

export const AI_BASE = '/ai'
const BASE = AI_BASE

export function listPrompts(): Promise<{ items: PromptTemplate[]; models: AiModel[]; categories: TemplateCategory[]; code_tables: SystemCodeTable[] }> {
  return request(http.get(`${BASE}/prompts`))
}

/** 编辑页：只取这一个模板（新建时不传）和模型、类型、系统码表的选项 */
export function promptEditorData(promptId?: string): Promise<{ item: PromptTemplate | null; models: AiModel[]; categories: TemplateCategory[]; code_tables: SystemCodeTable[] }> {
  return request(http.get(`${BASE}/prompts/editor`, { params: { prompt_id: promptId || undefined } }))
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

/** version 是管理员核对时看到的草稿版本号：这期间草稿又被改过，后端拒绝上线（409），免得上线一份没人核对过的内容。 */
export function publishPrompt(id: string, version: number): Promise<PromptTemplate> {
  return request(http.post(`${BASE}/prompts/${id}/release`, { version }))
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

/** release：跑模板的上线版本；draft：跑已保存的草稿（批量任务不用等上线，定时任务只跑上线版本） */
export type RunVersion = 'release' | 'draft'

/** 选好数据文件后的检查结果：按哪一版、哪个模型跑多少行 */
export interface BatchInputSummary { name: string; rows: number; headers: string[]; version: RunVersion; release_no: number | null; model_name: string }

export function previewBatchInput(promptId: string, version: RunVersion, file: File): Promise<BatchInputSummary> {
  const form = new FormData()
  form.append('file', file)
  return request(http.post(`${BASE}/batch-runs/input-preview`, form, { params: { prompt_id: promptId, version }, timeout: 300_000 }))
}

/** limit 为 0 跑全部；其余参数放 query，文件放 multipart。 */
export function startBatchRun(payload: { prompt_id: string; version: RunVersion; thinking: boolean; limit: number }, file: File): Promise<BatchRun> {
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
  /** 样本试跑和上一次对比时才有：上一次这一行的结果 */
  previous?: Pick<RunRow, 'status' | 'items' | 'error' | 'answer'> | null
  /** fixed：上次有问题这次成功；broke：上次成功这次有问题；changed：两次都成功但字段不同 */
  change?: RowChange
}

export type RowChange = 'fixed' | 'broke' | 'changed' | ''

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

/** 码表预览：名称、整份多少字多少行、前 200 行。每次提问都把整份放进 @【上传码表】。 */
export interface CodePreview {
  name: string
  chars: number
  lines: number
  head: string
  truncated: boolean
}

/** 系统码表现在的内容，不用先保存模板。 */
export function previewSystemCode(key: string): Promise<CodePreview> {
  return request(http.get(`${BASE}/prompts/code-preview`, { params: { code_table: key } }))
}

/** 模板上传的码表文件。 */
export function previewUploadedCode(promptId: string): Promise<CodePreview> {
  return request(http.get(`${BASE}/prompts/${promptId}/code-preview`))
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

/** 只跑了前几行的任务：用同一份数据、同一版提示词新建一个跑全部的任务，前面答好的行沿用 */
export function runAllBatchRun(id: string): Promise<BatchRun & { reused_rows: number }> {
  return request(http.post(`${BASE}/batch-runs/${id}/run-all`))
}

export function stopBatchRun(id: string): Promise<BatchRun> {
  return request(http.post(`${BASE}/batch-runs/${id}/stop`))
}

export function deleteBatchRun(id: string): Promise<null> {
  return request(http.delete(`${BASE}/batch-runs/${id}`))
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
