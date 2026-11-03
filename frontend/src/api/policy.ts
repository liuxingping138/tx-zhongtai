import { postExcelImport, type ImportResult, type ImportStage } from './excelImport'
import { http, request } from './http'
import type { FilterParam, Page } from './types'

export interface SourceItem {
  id: string
  internal_id: string
  site_code: string
  province_name: string
  province_code: string
  city_name: string
  city_code: string
  district_name: string
  district_code: string
  site_name: string
  site_type: string
  crawler_status: string
  online_date: string
  crawl_priority: string
  url: string
  tag: string
  data_type: string
  department: string
  version: number
  created_at: string
  created_by_name: string
  updated_at: string
  updated_by_name: string
}

export interface BaseTagItem {
  id: string
  policy_name: string
  /** 类型判断失败 / 待解读 / 已完成…；手工录入的为空 */
  ai_status: string
  issuing_dept: string
  issuer_industry: string
  policy_level: string
  province_code: string
  province_name: string
  city_code: string
  city_name: string
  issued_at: string
  policy_types: string
  source_url: string
  is_penetrate: string
  penetrate_words: string
  penetrate_score: string
  need_interpret: string
  remark: string
  version: number
  created_at: string
  created_by_name: string
  updated_at: string
  updated_by_name: string
}

export interface InterpretationItem {
  id: string
  record_id: string
  tenant_id: string
  policy_uid: string
  policy_title: string
  industry_scenario_code: string
  industry_code: string
  industry_l1: string
  industry_l2: string
  industry_l3: string
  scenario_code: string
  scenario_l1_name: string
  scenario_l2_name: string
  scenario_l3_name: string
  target_customers: string
  adapted_products: string
  purchase_reason: string
  relation_key: string
  opportunity_type: string
  policy_summary: string
  has_subsidy: string
  subsidy_content: string
  market_opportunity: string
  info_level: string
  is_new_scenario: string
  new_scenario_level: string
  remark: string
  data_status: string
  /** 和行业场景码表比对的结果：码表已有、待审、已采纳、已合并、已驳回、重复、行业不在码表、场景不完整；空为还没比对 */
  scenario_state: string
  /** 新增场景归到的候选（新增场景审核里的一个场景） */
  candidate_id: string
  /** AI 解读写入的行才有：源政策ID、解读时间 */
  source_content_id: string
  tagged_at: string
  /** 新增场景按决定写进码表、回填编码的时间 */
  scenario_synced_at: string
  version: number
  created_at: string
  created_by_name: string
  updated_at: string
  updated_by_name: string
}

export type { ImportResult } from './excelImport'

export function listSources(params: {
  site_name?: FilterParam
  province_name?: FilterParam
  city_name?: FilterParam
  tag?: FilterParam
  site_code?: FilterParam
  crawl_priority?: FilterParam
  site_type?: FilterParam
  crawler_status?: FilterParam
  /** 上线时间区间，YYYY-MM-DD，含两端 */
  online_date_from?: string
  online_date_to?: string
  page?: number
  page_size?: number
}): Promise<Page<SourceItem>> {
  return request(http.get('/policy/sources', { params }))
}

export function createSource(body: Partial<SourceItem>): Promise<SourceItem> {
  return request(http.post('/policy/sources', body))
}

export function updateSource(id: string, body: Partial<SourceItem> & { version: number }): Promise<SourceItem> {
  return request(http.patch(`/policy/sources/${id}`, body))
}

/** 勾选多条批量改政策解读的数据状态（待验证 / 人工验证）。 */
export function setInterpretationsDataStatus(ids: string[], dataStatus: string): Promise<{ updated: number; unchanged: number }> {
  return request(http.post('/policy/interpretations/data-status', { ids, data_status: dataStatus }))
}

/** 勾选多条批量改爬虫状态；改成「已爬」的上线时间由后端记为当天。 */
export function setSourcesCrawlerStatus(ids: string[], crawlerStatus: string): Promise<{ updated: number; unchanged: number }> {
  return request(http.post('/policy/sources/crawler-status', { ids, crawler_status: crawlerStatus }))
}

export function clearSources(): Promise<{ deleted: number }> {
  return request(http.post('/policy/sources/clear', { confirm: '清空' }))
}

export function importSources(
  file: File,
  onProgress?: (percent: number, stage: ImportStage) => void,
): Promise<ImportResult> {
  return postExcelImport('/policy/sources/import', file, onProgress)
}

export function listBaseTags(params: {
  policy_name?: FilterParam
  province_name?: FilterParam
  policy_types?: FilterParam
  is_penetrate?: FilterParam
  need_interpret?: FilterParam
  ai_status?: FilterParam
  page?: number
  page_size?: number
}): Promise<Page<BaseTagItem>> {
  return request(http.get('/policy/base-tags', { params }))
}

export function getBaseTag(id: string): Promise<BaseTagItem> {
  return request(http.get(`/policy/base-tags/${id}`))
}

export function updateBaseTag(id: string, body: Partial<BaseTagItem> & { version: number }): Promise<BaseTagItem> {
  return request(http.patch(`/policy/base-tags/${id}`, body))
}

export function importBaseTags(
  file: File,
  onProgress?: (percent: number, stage: ImportStage) => void,
): Promise<ImportResult> {
  return postExcelImport('/policy/base-tags/import', file, onProgress)
}

export function listInterpretations(params: {
  policy_title?: FilterParam
  industry_l1?: FilterParam
  scenario_l1_name?: FilterParam
  opportunity_type?: FilterParam
  is_new_scenario?: FilterParam
  new_scenario_level?: FilterParam
  info_level?: FilterParam
  data_status?: FilterParam
  scenario_state?: FilterParam
  page?: number
  page_size?: number
}): Promise<Page<InterpretationItem>> {
  return request(http.get('/policy/interpretations', { params }))
}

export function getInterpretation(id: string): Promise<InterpretationItem> {
  return request(http.get(`/policy/interpretations/${id}`))
}

export function updateInterpretation(
  id: string,
  body: Partial<InterpretationItem> & { version: number },
): Promise<InterpretationItem> {
  return request(http.patch(`/policy/interpretations/${id}`, body))
}

export function importInterpretations(
  file: File,
  onProgress?: (percent: number, stage: ImportStage) => void,
): Promise<ImportResult> {
  return postExcelImport('/policy/interpretations/import', file, onProgress)
}


/** 政策正文：平台库里不存，点开详情时按源政策 ID 现读源库，文字和打标发给模型的同一口径。 */
export interface PolicyContent {
  title: string
  text: string
  source_url: string
  issued_at: string
  chars: number
}

export function getBaseTagContent(id: string): Promise<PolicyContent> {
  return request(http.get(`/policy/base-tags/${id}/content`))
}

export function getInterpretationContent(id: string): Promise<PolicyContent> {
  return request(http.get(`/policy/interpretations/${id}/content`))
}
