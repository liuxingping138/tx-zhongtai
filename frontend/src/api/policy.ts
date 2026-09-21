import { postExcelImport, type ImportResult, type ImportStage } from './excelImport'
import { http, request } from './http'
import type { Page } from './types'

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
  relation_key: string
  opportunity_type: string
  policy_summary: string
  has_subsidy: string
  subsidy_content: string
  market_opportunity: string
  info_level: string
  is_new_scenario: string
  new_scenario_level: string
  version: number
  created_at: string
  created_by_name: string
  updated_at: string
  updated_by_name: string
}

export type { ImportResult } from './excelImport'

export type FilterOptions = Record<string, string[] | Record<string, string[]>>

export function listSources(params: {
  site_name?: string
  province_name?: string
  city_name?: string
  tag?: string
  site_code?: string
  crawl_priority?: string
  page?: number
  page_size?: number
}): Promise<Page<SourceItem>> {
  return request(http.get('/policy/sources', { params }))
}

export function sourceOptions(): Promise<FilterOptions> {
  return request(http.get('/policy/sources/options'))
}

export function createSource(body: Partial<SourceItem>): Promise<SourceItem> {
  return request(http.post('/policy/sources', body))
}

export function updateSource(id: string, body: Partial<SourceItem> & { version: number }): Promise<SourceItem> {
  return request(http.patch(`/policy/sources/${id}`, body))
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

export function baseTagOptions(): Promise<FilterOptions> {
  return request(http.get('/policy/base-tags/options'))
}

export function listBaseTags(params: {
  policy_name?: string
  province_name?: string
  policy_types?: string
  is_penetrate?: string
  need_interpret?: string
  page?: number
  page_size?: number
}): Promise<Page<BaseTagItem>> {
  return request(http.get('/policy/base-tags', { params }))
}

export function createBaseTag(body: Partial<BaseTagItem>): Promise<BaseTagItem> {
  return request(http.post('/policy/base-tags', body))
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

export function interpretationOptions(): Promise<FilterOptions> {
  return request(http.get('/policy/interpretations/options'))
}

export function listInterpretations(params: {
  policy_title?: string
  industry_scenario_code?: string
  industry_l1?: string
  opportunity_type?: string
  page?: number
  page_size?: number
}): Promise<Page<InterpretationItem>> {
  return request(http.get('/policy/interpretations', { params }))
}

export function createInterpretation(body: Partial<InterpretationItem>): Promise<InterpretationItem> {
  return request(http.post('/policy/interpretations', body))
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

