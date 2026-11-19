import type { AxiosResponse } from 'axios'

import { postExcelImport, type ImportResult, type ImportStage } from './excelImport'
import { http, request } from './http'
import type { FilterParam, Page } from './types'

export interface KnowledgeItem {
  id: string
  file_name: string
  file_type: string
  operator_type: string
  depart_affiliation: string
  industry_type: string
  app_scenario: string
  market_category: string
  product_type: string
  product_sub_type: string
  prov_name: string
  data_time: string
  uploaded_at: string
  file_suffix: string
  file_size_bytes: number
  file_size_display: string
  remark: string
  is_defined: boolean
  is_favorited: boolean
  can_export: boolean
  can_edit: boolean
  version: number
  created_at: string
  created_by_name: string
  updated_at: string
  updated_by_name: string
}

export interface KnowledgeAccessSummary {
  readable_file_types: string[]
  exportable_file_types: string[]
  editable_file_types: string[]
  readable_industries: string[]
  exportable_industries: string[]
  editable_industries: string[]
}

export interface KnowledgeOpLogItem {
  id: string
  file_id: string
  actor_id: string
  actor_name: string
  op_type: string
  detail: string
  created_at: string
}

export interface KnowledgePreviewPayload {
  item: KnowledgeItem
  preview: {
    mode: 'pdf' | 'text' | 'summary'
    has_binary: boolean
    content_text: string
  }
}

export interface KnowledgeQuery {
  file_name?: FilterParam
  file_type?: FilterParam
  operator_type?: FilterParam
  product_type?: FilterParam
  product_sub_type?: FilterParam
  industry_type?: FilterParam
  prov_name?: FilterParam
  app_scenario?: FilterParam
  depart_affiliation?: FilterParam
  market_category?: FilterParam
  data_time?: FilterParam
  tag_status?: FilterParam
  favorite_only?: FilterParam
  page?: number
  page_size?: number
}

export interface KnowledgeUploadMetadata {
  file_type?: string
  operator_type?: string
  depart_affiliation?: string
  industry_type?: string
  app_scenario?: string
  market_category?: string
  product_type?: string
  product_sub_type?: string
  prov_name?: string
  data_time?: string
  remark?: string
}

export type { ImportResult } from './excelImport'

export function getKnowledgeAccess(): Promise<KnowledgeAccessSummary> {
  return request(http.get('/thinktank/knowledge/access'))
}

export function listKnowledge(params: KnowledgeQuery): Promise<Page<KnowledgeItem>> {
  return request(http.get('/thinktank/knowledge', { params }))
}

export function getKnowledge(id: string): Promise<KnowledgeItem> {
  return request(http.get(`/thinktank/knowledge/${id}`))
}

export function previewKnowledge(id: string): Promise<KnowledgePreviewPayload> {
  return request(http.get(`/thinktank/knowledge/${id}/preview`))
}

export function fetchKnowledgeContentBlob(id: string): Promise<AxiosResponse<Blob>> {
  return http.get(`/thinktank/knowledge/${id}/content`, { responseType: 'blob', timeout: 600_000 })
}

export function downloadKnowledgeBlob(id: string): Promise<AxiosResponse<Blob>> {
  return http.get(`/thinktank/knowledge/${id}/download`, { responseType: 'blob', timeout: 600_000 })
}

export function favoriteKnowledge(id: string): Promise<{ id: string; is_favorited: boolean }> {
  return request(http.post(`/thinktank/knowledge/${id}/favorite`))
}

export function unfavoriteKnowledge(id: string): Promise<{ id: string; is_favorited: boolean }> {
  return request(http.delete(`/thinktank/knowledge/${id}/favorite`))
}

export function listKnowledgeLogs(
  id: string,
  params?: { page?: number; page_size?: number },
): Promise<Page<KnowledgeOpLogItem>> {
  return request(http.get(`/thinktank/knowledge/${id}/logs`, { params }))
}

export function updateKnowledge(
  id: string,
  body: Partial<KnowledgeItem> & { version: number },
): Promise<KnowledgeItem> {
  return request(http.patch(`/thinktank/knowledge/${id}`, body))
}

export function deleteKnowledge(id: string): Promise<{ deleted: boolean }> {
  return request(http.delete(`/thinktank/knowledge/${id}`))
}

export function uploadKnowledgeFile(
  file: File,
  metadata: KnowledgeUploadMetadata = {},
): Promise<KnowledgeItem> {
  const form = new FormData()
  form.append('file', file)
  return request(http.post('/thinktank/knowledge/upload', form, { params: metadata, timeout: 180_000 }))
}

export function uploadKnowledgeTags(
  file: File,
  onProgress?: (percent: number, stage: ImportStage) => void,
): Promise<ImportResult> {
  return postExcelImport('/thinktank/knowledge/upload-tags', file, onProgress, 180_000)
}

export function exportUndefinedKnowledge(): Promise<AxiosResponse<Blob>> {
  return http.get('/thinktank/knowledge/export-undefined', {
    responseType: 'blob',
    timeout: 600_000,
  })
}
