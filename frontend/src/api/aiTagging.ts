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

export interface AiTaggingOverview {
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
export const listAiTaggingRuns = (page: number) =>
  request<Page<AiTaggingRun>>(http.get(`${base}/runs`, { params: { page, page_size: 10 } }))
