import { postExcelImport, type ImportResult, type ImportStage } from './excelImport'
import { getAccessToken, getCsrfToken } from './session'
import { http, request } from './http'
import type { Page } from './types'

export interface PolicyTypeItem {
  id: string
  seq_no: string
  type_name: string
  definition: string
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
}

export type { ImportResult } from './excelImport'

export type FilterOptions = Record<string, string[]>

export function listPolicyTypes(params: { keyword?: string; page?: number; page_size?: number }): Promise<Page<PolicyTypeItem>> {
  return request(http.get('/codebook/policy-types', { params }))
}

export function policyTypeOptions(): Promise<FilterOptions> {
  return request(http.get('/codebook/policy-types/options'))
}

export function createPolicyType(body: { seq_no?: string; type_name: string; definition?: string }): Promise<PolicyTypeItem> {
  return request(http.post('/codebook/policy-types', body))
}

export function updatePolicyType(
  id: string,
  body: { seq_no?: string; type_name: string; definition?: string; version: number },
): Promise<PolicyTypeItem> {
  return request(http.patch(`/codebook/policy-types/${id}`, body))
}

export function importPolicyTypes(
  file: File,
  onProgress?: (percent: number, stage: ImportStage) => void,
): Promise<ImportResult> {
  return postExcelImport('/codebook/policy-types/import', file, onProgress, 180_000)
}

export function scenarioOptions(): Promise<FilterOptions> {
  return request(http.get('/codebook/scenarios/options'))
}

export function listScenarios(params: {
  industry_scenario_code?: string
  industry_l1?: string
  scenario_tag?: string
  customer_group_name?: string
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

export function areaCodeOptions(): Promise<FilterOptions> {
  return request(http.get('/codebook/area-codes/options'))
}

export function listAreaCodes(params: {
  prov_name?: string
  city_name?: string
  county_name?: string
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
  const headers: Record<string, string> = {}
  const token = getAccessToken()
  const csrf = getCsrfToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  if (csrf) {
    headers['X-CSRF-Token'] = csrf
  }
  const body = new FormData()
  body.append('file', file)
  onProgress?.(10, 'upload')
  let response: Response
  try {
    response = await fetch('/api/v1/codebook/area-codes/resolve', {
      method: 'POST',
      headers,
      body,
      credentials: 'include',
      signal: AbortSignal.timeout(600_000),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new Error('补全省市区编码超时，请拆成更小的文件再上传')
    }
    throw error
  }
  onProgress?.(80, 'parse')
  if (!response.ok) {
    throw new Error('补全省市区编码失败')
  }
  return {
    matched: Number(response.headers.get('X-Matched-Count') || 0),
    unmatched: Number(response.headers.get('X-Unmatched-Count') || 0),
    blob: await response.blob(),
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

export async function downloadCodebook(path: string, filename: string): Promise<void> {
  const headers: Record<string, string> = {}
  const token = getAccessToken()
  const csrf = getCsrfToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  if (csrf) {
    headers['X-CSRF-Token'] = csrf
  }
  const response = await fetch(`/api/v1${path}`, { headers, credentials: 'include' })
  if (!response.ok) {
    throw new Error('导出失败')
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.hidden = true
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Give browsers time to consume the blob URL before releasing it.
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
