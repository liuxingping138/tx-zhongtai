import { http, request } from './http'
import type { FilterParam, Page } from './types'

/** 新增场景候选：AI 解读出的、码表里还没有的场景，按第一个新出现的那一级归成一个，人在这里做决定。 */
export interface CandidateItem {
  id: string
  /** 新场景、新关联（各级场景码表里都有，只是没挂在这个行业下） */
  kind: string
  new_level: number
  /** 一级、二级、三级、新关联 */
  level_label: string
  /** 新的那一级的名称；新关联是整条场景路径 */
  name: string
  scenario_l1: string
  scenario_l2: string
  scenario_l3: string
  /** 挂在哪个已有场景下（新的一级场景为空） */
  parent: string
  /** 新关联要挂的行业 */
  industry: string
  status: string
  adopted_name: string
  target: string
  target_l1: string
  target_l2: string
  target_l3: string
  reject_reason: string
  note: string
  decided_at: string
  decided_by_name: string
  row_count: number
  policy_count: number
  industry_count: number
  main_industry: string
  sample_title: string
  similar_name: string
  similar_score: number
  /** 高、中、无；空为还没算 */
  similar_level: string
  first_seen_at: string
  last_seen_at: string
  version: number
}

export interface CandidateSummary {
  by_status: Record<string, number>
  pending_rows: number
  pending_similar: number
  new_today: number
}

export interface CandidateDetail extends CandidateItem {
  industries: { path: string; rows: number }[]
  /** 下级新场景，例如新的二级下面 AI 写的三级 */
  children: { path: string; rows: number }[]
  /** AI 给的理由里最常见的几条 */
  reasons: { text: string; count: number }[]
}

export interface CandidateContext {
  /** 要挂的位置下码表里已有的场景和它们的下级数 */
  siblings: { name: string; children: number }[]
  /** 码表里字面最像的已有场景 */
  similar: { path: string[]; score: number; level: string; desc: string }[]
  /** 这个场景路径已经挂在哪些行业下（新关联用） */
  industries: string[]
}

export interface CandidateRow {
  id: string
  policy_title: string
  created_at: string
  industry: string
  industry_l1: string
  industry_l2: string
  industry_l3: string
  scenario_l1_name: string
  scenario_l2_name: string
  scenario_l3_name: string
  opportunity_type: string
  remark: string
  scenario_state: string
  version: number
}

export interface CandidateQuery {
  status?: FilterParam
  keyword?: FilterParam
  industry_l1?: FilterParam
  level_label?: FilterParam
  similar_level?: FilterParam
  min_policies?: number | string
  page?: number
  page_size?: number
}

export function listCandidates(params: CandidateQuery): Promise<Page<CandidateItem> & { summary: CandidateSummary }> {
  return request(http.get('/policy/scenario-candidates', { params }))
}

export function candidateOptions(): Promise<{
  options: Record<string, { items: string[]; truncated: boolean }>
  reject_reasons: string[]
}> {
  return request(http.get('/policy/scenario-candidates/options'))
}

export function getCandidate(id: string): Promise<CandidateDetail> {
  return request(http.get(`/policy/scenario-candidates/${id}`))
}

export function getCandidateContext(id: string): Promise<CandidateContext> {
  return request(http.get(`/policy/scenario-candidates/${id}/context`))
}

export function listCandidateRows(
  id: string,
  params: { keyword?: string; page?: number; page_size?: number } = {},
): Promise<Page<CandidateRow>> {
  return request(http.get(`/policy/scenario-candidates/${id}/rows`, { params }))
}

export function adoptCandidate(id: string, body: { version: number; name?: string }): Promise<CandidateItem> {
  return request(http.post(`/policy/scenario-candidates/${id}/adopt`, body))
}

export function mergeCandidate(id: string, body: { version: number; target: string[] }): Promise<CandidateItem> {
  return request(http.post(`/policy/scenario-candidates/${id}/merge`, body))
}

export function rejectCandidate(
  id: string,
  body: { version: number; reason: string; note?: string },
): Promise<CandidateItem> {
  return request(http.post(`/policy/scenario-candidates/${id}/reject`, body))
}

export function reopenCandidate(id: string, body: { version: number }): Promise<CandidateItem> {
  return request(http.post(`/policy/scenario-candidates/${id}/reopen`, body))
}

/** 只改这一行解读的行业场景（来源政策里逐行纠正），编码按码表回填 */
export function changeRowScenario(
  id: string,
  body: {
    version: number
    industry_l1: string
    industry_l2: string
    industry_l3: string
    scenario_l1_name: string
    scenario_l2_name: string
    scenario_l3_name: string
  },
): Promise<{ id: string; scenario_state: string; version: number }> {
  return request(http.post(`/policy/interpretations/${id}/scenario`, body))
}
