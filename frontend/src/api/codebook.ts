
import { isApiError } from './errors'
import { postExcelImport, type ImportResult, type ImportStage } from './excelImport'
import { http, request } from './http'
import type { FilterParam, Page } from './types'

export interface PolicyTypeItem {
  id: string
  seq_no: string
  type_name: string
  definition: string
  /** AI 打政策类型时多个命中按它排序，如 P0 最先 */
  priority: string
  version: number
  created_at: string
  created_by_name: string
  updated_at: string
  updated_by_name: string
}

export interface ScenarioItem {
  id: string
  version: number
  created_at: string
  created_by_name: string
  updated_at: string
  updated_by_name: string
  industry_scenario_code: string
  industry_code: string
  industry_l1: string
  industry_l2: string
  industry_l3: string
  scenario_tag: string
  scenario_level: string
  scenario_type: string
  desc_90: string
  desc_130: string
  desc_pest: string
  scenario_source: string
  scenario_hierarchy: string
  scenario_code: string
  scenario_l1_name: string
  scenario_l1_desc: string
  scenario_l2_name: string
  scenario_l2_desc: string
  scenario_l3_name: string
  scenario_l3_desc: string
  customer_group_name: string
  customer_group_industry: string
  org_keywords: string
  scope_keywords: string
  customer_level: string
  customer_category: string
  product_l1_name: string
  product_l2_name: string
  branch_count: string
  product_l1_sort: string
  product_l2_sort: string
  /** 同步新增场景时写：政策解读里人工确认后进码表的标「是」。 */
  is_new_scenario: string
  source_policy: string
}

export type { ImportResult } from './excelImport'

export function listPolicyTypes(params: { keyword?: FilterParam; page?: number; page_size?: number }): Promise<Page<PolicyTypeItem>> {
  return request(http.get('/codebook/policy-types', { params }))
}

export function createPolicyType(body: { seq_no?: string; type_name: string; definition?: string; priority?: string }): Promise<PolicyTypeItem> {
  return request(http.post('/codebook/policy-types', body))
}

export function updatePolicyType(
  id: string,
  body: { seq_no?: string; type_name: string; definition?: string; priority?: string; version: number },
): Promise<PolicyTypeItem> {
  return request(http.patch(`/codebook/policy-types/${id}`, body))
}

export function importPolicyTypes(
  file: File,
  onProgress?: (percent: number, stage: ImportStage) => void,
): Promise<ImportResult> {
  return postExcelImport('/codebook/policy-types/import', file, onProgress, 180_000)
}

export function listScenarios(params: {
  industry_scenario_code?: FilterParam
  industry_l1?: FilterParam
  scenario_tag?: FilterParam
  customer_group_name?: FilterParam
  is_new_scenario?: FilterParam
  page?: number
  page_size?: number
}): Promise<Page<ScenarioItem>> {
  return request(http.get('/codebook/scenarios', { params }))
}

export function getScenario(id: string): Promise<ScenarioItem> {
  return request(http.get(`/codebook/scenarios/${id}`))
}

export function createScenario(body: Partial<ScenarioItem>): Promise<ScenarioItem> {
  return request(http.post('/codebook/scenarios', body))
}

export function updateScenario(id: string, body: Partial<ScenarioItem> & { version: number }): Promise<ScenarioItem> {
  return request(http.patch(`/codebook/scenarios/${id}`, body))
}

export function importScenarios(
  file: File,
  onProgress?: (percent: number, stage: ImportStage) => void,
): Promise<ImportResult> {
  return postExcelImport('/codebook/scenarios/import', file, onProgress, 180_000)
}

export interface AreaCodeItem {
  id: string
  version: number
  created_at: string
  created_by_name: string
  updated_at: string
  updated_by_name: string
  prov_id: string
  prov_name: string
  city_id: string
  city_name: string
  county_id: string
  county_name: string
  alias_prov_name: string
  alias_city_name: string
  alias_county_name: string
  city_name_short: string
  county_name_short: string
}

export function listAreaCodes(params: {
  prov_name?: FilterParam
  city_name?: FilterParam
  county_name?: FilterParam
  page?: number
  page_size?: number
}): Promise<Page<AreaCodeItem>> {
  return request(http.get('/codebook/area-codes', { params }))
}

export function createAreaCode(body: Partial<AreaCodeItem>): Promise<AreaCodeItem> {
  return request(http.post('/codebook/area-codes', body))
}

export function updateAreaCode(id: string, body: Partial<AreaCodeItem> & { version: number }): Promise<AreaCodeItem> {
  return request(http.patch(`/codebook/area-codes/${id}`, body))
}

export function importAreaCodes(
  file: File,
  onProgress?: (percent: number, stage: ImportStage) => void,
): Promise<ImportResult> {
  return postExcelImport('/codebook/area-codes/import', file, onProgress, 180_000)
}

export async function resolveAreaCodes(
  file: File,
  onProgress?: (percent: number, stage: ImportStage) => void,
): Promise<{ matched: number; unmatched: number; blob: Blob }> {
  const body = new FormData()
  body.append('file', file)
  onProgress?.(10, 'upload')
  try {
    const response = await http.post<Blob>('/codebook/area-codes/resolve', body, {
      responseType: 'blob',
      timeout: 600_000,
      onUploadProgress(event) {
        if (!event.total) return
        onProgress?.(Math.min(70, Math.round((event.loaded / event.total) * 70)), 'upload')
      },
    })
    onProgress?.(80, 'parse')
    const matched = Number(response.headers['x-matched-count'] || 0)
    const unmatched = Number(response.headers['x-unmatched-count'] || 0)
    return { matched, unmatched, blob: response.data }
  } catch (error) {
    if (isApiError(error) && error.code === 'TIMEOUT') {
      throw new Error('补全省市区编码超时，请拆成更小的文件再上传')
    }
    throw error
  }
}

export async function importAfterAreaResolve(
  file: File,
  importer: (ready: File, onProgress?: (percent: number, stage: ImportStage) => void) => Promise<ImportResult>,
  onProgress?: (percent: number, stage: ImportStage) => void,
): Promise<ImportResult> {
  const resolved = await resolveAreaCodes(file, onProgress)
  const ready = new File([resolved.blob], file.name, {
    type: file.type || 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  return importer(ready, onProgress)
}

