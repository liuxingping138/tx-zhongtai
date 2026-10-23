import { http, request } from './http'

/** 政策 AI 打标的三个任务，在任务调度里各是一个任务（调度编码 = job_code）。 */
export type AiTaskCode = 'type' | 'interpret' | 'opportunity'

/** 正在跑的那一批：在做什么、AI 答到第几条（ai-service 暂时取不到时 done、total 为空） */
export interface AiTaggingCurrent {
  id: string
  stage: string
  stage_name: string
  started_at: string
  cost: string
  done: number | null
  total: number | null
}

/** 一个打标任务的设置和今天的花费。读取进度只有类型判断有：采集日期 + 该日已读到的正文ID。 */
export interface AiTask {
  code: AiTaskCode
  job_code: string
  name: string
  prompt_id: string
  batch_size: number
  content_max_chars: number
  daily_cost_limit: string
  cursor_date: string
  cursor_content_id: string
  version: number
  updated_at: string
  updated_by_name: string
  spent_today: string
  spent_month: string
  current: AiTaggingCurrent | null
  /** 待办条数：类型判断是等着重新判断的，解读、市场机会是等着做的 */
  pending: number
}

/** 可以给打标任务用的模板：政策类、已上线 */
export interface OnlineTemplate {
  prompt_id: string
  title: string
  release_no: number
  released_at: string
  model_id: string
  output_fields: string[]
  code: string
}

export type AiTaskBody = Pick<AiTask, 'prompt_id' | 'batch_size' | 'content_max_chars' | 'daily_cost_limit' | 'cursor_date' | 'version'>

const base = '/policy/ai-tagging'
export const listAiTasks = () => request<{ items: AiTask[] }>(http.get(`${base}/tasks`))
export const listAiTemplates = () => request<{ items: OnlineTemplate[]; error: string }>(http.get(`${base}/templates`))
/** 基础标签列表上勾选政策重新打标：放回某个任务的待办，下次执行那个任务时处理。 */
export interface RetagResult {
  step: AiTaskCode
  task: string
  queued: number
  skipped: { reason: string; count: number }[]
}
export const requestRetag = (ids: string[], step: AiTaskCode) => request<RetagResult>(http.post(`${base}/retag`, { ids, step }))
export const updateAiTask = (code: AiTaskCode, body: AiTaskBody) => request<AiTask>(http.put(`${base}/tasks/${code}`, body))
