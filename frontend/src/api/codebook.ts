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

export interface ImportResult {
  inserted: number
  updated: number
  skipped: number
  total: number
}

export function listPolicyTypes(params: { keyword?: string; page?: number; page_size?: number }): Promise<Page<PolicyTypeItem>> {
  return request(http.get('/codebook/policy-types', { params }))
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

export function importPolicyTypes(file: File): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  return request(http.post('/codebook/policy-types/import', form, { timeout: 180_000 }))
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

export function importScenarios(file: File): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  return request(http.post('/codebook/scenarios/import', form, { timeout: 180_000 }))
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
  link.click()
  URL.revokeObjectURL(url)
}
