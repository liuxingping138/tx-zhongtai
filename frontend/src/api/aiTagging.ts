import { http, request } from './http'
import type { Page } from './types'
import type { AiTaggingResult } from './scheduler'

/** 政策 AI 打标的设置。读取进度 = 采集日期 + 该日已读到的正文ID，改起始日期会从那天第一条重读。 */
export interface AiTaggingConfig {
  type_prompt_id: string
  interpret_prompt_id: string
  opportunity_prompt_id: string
  batch_size: number
  content_max_chars: number
  daily_cost_limit: string
  cursor_date: string
  cursor_content_id: string
  version: number
  updated_at: string
  updated_by_name: string
}

/** 可以给定时任务用的模板：政策类、已上线 */
export interface OnlineTemplate {
  prompt_id: string
  title: string
  release_no: number
  released_at: string
  model_id: string
  output_fields: string[]
  code: string
}

/** 正在跑的那一批：第几步、这一步 AI 答到第几条（ai-service 暂时取不到时 done、total 为空） */
export interface AiTaggingCurrent {
  id: string
  stage: string
  stage_name: string
  started_at: string
  cost: string
  done: number | null
  total: number | null
}

export interface AiTaggingOverview {
  current: AiTaggingCurrent | null
  config: AiTaggingConfig
  templates: OnlineTemplate[]
  templates_error: string
  spent_today: string
  spent_month: string
}

export interface AiTaggingRun extends AiTaggingResult {
  id: string
  started_at: string
  finished_at: string
}

export type AiTaggingConfigBody = Omit<AiTaggingConfig, 'cursor_content_id' | 'updated_at' | 'updated_by_name'>

const base = '/policy/ai-tagging'
export const aiTaggingOverview = () => request<AiTaggingOverview>(http.get(base))
export const updateAiTaggingConfig = (body: AiTaggingConfigBody) => request<AiTaggingConfig>(http.put(`${base}/config`, body))
export interface BillingDay {
  day: string
  runs: number
  cost: string
  type_cost: string
  interpret_cost: string
  opportunity_cost: string
  source_rows: number
  tagged_rows: number
  interpret_rows: number
}

export interface AiTaggingBilling {
  days: number
  items: BillingDay[]
  total: Pick<BillingDay, 'cost' | 'type_cost' | 'interpret_cost' | 'opportunity_cost'>
}

export const aiTaggingBilling = (days: number) => request<AiTaggingBilling>(http.get(`${base}/billing`, { params: { days } }))
export const listAiTaggingRuns = (page: number) =>
  request<Page<AiTaggingRun>>(http.get(`${base}/runs`, { params: { page, page_size: 10 } }))
