import type { AxiosResponse } from 'axios'

import { postExcelImport, type ImportResult, type ImportStage } from './excelImport'
import { http, request } from './http'
import type { FilterParam, Page } from './types'

export type { ImportResult } from './excelImport'

export type ThinktankLibraryKey = 'knowledge' | 'reports' | 'proposals'

export interface ThinktankPreviewInfo {
  mode: 'pdf' | 'text' | 'summary'
  has_binary: boolean
  content_text: string
}

export interface ThinktankFavoriteResult {
  id: string
  is_favorited: boolean
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

interface ThinktankBaseItem {
  id: string
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

export interface KnowledgeItem extends ThinktankBaseItem {
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
}

export interface KnowledgeAccessSummary {
  readable_file_types: string[]
  exportable_file_types: string[]
  editable_file_types: string[]
  readable_industries: string[]
  exportable_industries: string[]
  editable_industries: string[]
}

export interface KnowledgePreviewPayload {
  item: KnowledgeItem
  preview: ThinktankPreviewInfo
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

export interface ReportItem extends ThinktankBaseItem {
  report_name: string
  project_name: string
  customer_name: string
  report_type: string
  industry_tags: string
  region_tag: string
  delivery_dept: string
  participants: string
  is_temp_support: string
  delivery_date: string
  summary: string
  keywords: string
  data_sources: string
}

export interface ReportQuery {
  report_name?: FilterParam
  project_name?: FilterParam
  customer_name?: FilterParam
  report_type?: FilterParam
  industry_tags?: FilterParam
  region_tag?: FilterParam
  delivery_dept?: FilterParam
  participants?: FilterParam
  is_temp_support?: FilterParam
  delivery_date?: FilterParam
  keywords?: FilterParam
  tag_status?: FilterParam
  favorite_only?: FilterParam
  page?: number
  page_size?: number
}

export interface ReportUploadMetadata {
  report_name?: string
  project_name?: string
  customer_name?: string
  report_type?: string
  industry_tags?: string
  region_tag?: string
  delivery_dept?: string
  participants?: string
  is_temp_support?: string
  delivery_date?: string
  summary?: string
  keywords?: string
  data_sources?: string
  remark?: string
}

export interface ReportPreviewPayload {
  item: ReportItem
  preview: ThinktankPreviewInfo
}

export interface ProposalItem extends ThinktankBaseItem {
  proposal_name: string
  customer_name: string
  proposal_type: string
  industry_tags: string
  region_tag: string
  opportunity_source: string
  bidding_method: string
  bid_deadline: string
  owner_dept: string
  owner_name: string
  quote_amount: string
  result_status: string
  win_amount: string
  selling_points: string
}

export interface ProposalQuery {
  proposal_name?: FilterParam
  customer_name?: FilterParam
  proposal_type?: FilterParam
  industry_tags?: FilterParam
  region_tag?: FilterParam
  opportunity_source?: FilterParam
  bidding_method?: FilterParam
  bid_deadline?: FilterParam
  owner_dept?: FilterParam
  owner_name?: FilterParam
  result_status?: FilterParam
  tag_status?: FilterParam
  favorite_only?: FilterParam
  page?: number
  page_size?: number
}

export interface ProposalUploadMetadata {
  proposal_name?: string
  customer_name?: string
  proposal_type?: string
  industry_tags?: string
  region_tag?: string
  opportunity_source?: string
  bidding_method?: string
  bid_deadline?: string
  owner_dept?: string
  owner_name?: string
  quote_amount?: string
  result_status?: string
  win_amount?: string
  selling_points?: string
  remark?: string
}

export interface ProposalPreviewPayload {
  item: ProposalItem
  preview: ThinktankPreviewInfo
}

export interface ThinktankFavoriteEntry {
  id: string
  library: ThinktankLibraryKey
  library_label: string
  title: string
  category_label: string
  industry_label: string
  region_label: string
  file_suffix: string
  file_size_display: string
  favorited_at: string
  updated_at: string
  can_export: boolean
  preview_path: string
}

export interface ThinktankFavoritesResponse {
  items: ThinktankFavoriteEntry[]
  total: number
  counts: { all: number; knowledge: number; reports: number; proposals: number }
}

export interface ThinktankFavoritesQuery {
  library?: 'all' | ThinktankLibraryKey
  keyword?: string
  page?: number
  page_size?: number
}

type LogPageParams = { page?: number; page_size?: number }
type ProgressFn = (percent: number, stage: ImportStage) => void

function postLibraryUpload<T>(path: string, file: File, metadata: object): Promise<T> {
  const form = new FormData()
  form.append('file', file)
  return request(http.post(path, form, { params: metadata, timeout: 180_000 }))
}

/* 资料库（/thinktank/knowledge） */
export const getKnowledgeAccess = (): Promise<KnowledgeAccessSummary> => request(http.get('/thinktank/knowledge/access'))
export const listKnowledge = (params: KnowledgeQuery): Promise<Page<KnowledgeItem>> => request(http.get('/thinktank/knowledge', { params }))
export const previewKnowledge = (id: string): Promise<KnowledgePreviewPayload> => request(http.get(`/thinktank/knowledge/${id}/preview`))
export const fetchKnowledgeContentBlob = (id: string, signal?: AbortSignal): Promise<AxiosResponse<Blob>> =>
  http.get(`/thinktank/knowledge/${id}/content`, { responseType: 'blob', timeout: 600_000, signal })
export const downloadKnowledgeBlob = (id: string): Promise<AxiosResponse<Blob>> =>
  http.get(`/thinktank/knowledge/${id}/download`, { responseType: 'blob', timeout: 600_000 })
export const favoriteKnowledge = (id: string): Promise<ThinktankFavoriteResult> => request(http.post(`/thinktank/knowledge/${id}/favorite`))
export const unfavoriteKnowledge = (id: string): Promise<ThinktankFavoriteResult> => request(http.delete(`/thinktank/knowledge/${id}/favorite`))
export const listKnowledgeLogs = (id: string, params?: LogPageParams): Promise<Page<KnowledgeOpLogItem>> =>
  request(http.get(`/thinktank/knowledge/${id}/logs`, { params }))
export const updateKnowledge = (id: string, body: Partial<KnowledgeItem> & { version: number }): Promise<KnowledgeItem> =>
  request(http.patch(`/thinktank/knowledge/${id}`, body))
export const deleteKnowledge = (id: string): Promise<{ deleted: boolean }> => request(http.delete(`/thinktank/knowledge/${id}`))
export const uploadKnowledgeFile = (file: File, metadata: KnowledgeUploadMetadata = {}): Promise<KnowledgeItem> =>
  postLibraryUpload('/thinktank/knowledge/upload', file, metadata)
export const uploadKnowledgeTags = (file: File, onProgress?: ProgressFn): Promise<ImportResult> =>
  postExcelImport('/thinktank/knowledge/upload-tags', file, onProgress, 180_000)
export const exportUndefinedKnowledge = (): Promise<AxiosResponse<Blob>> =>
  http.get('/thinktank/knowledge/export-undefined', { responseType: 'blob', timeout: 600_000 })

/* 报告库（/thinktank/reports） */
export const listReports = (params: ReportQuery): Promise<Page<ReportItem>> => request(http.get('/thinktank/reports', { params }))
export const previewReport = (id: string): Promise<ReportPreviewPayload> => request(http.get(`/thinktank/reports/${id}/preview`))
export const fetchReportContentBlob = (id: string, signal?: AbortSignal): Promise<AxiosResponse<Blob>> =>
  http.get(`/thinktank/reports/${id}/content`, { responseType: 'blob', timeout: 600_000, signal })
export const downloadReportBlob = (id: string): Promise<AxiosResponse<Blob>> =>
  http.get(`/thinktank/reports/${id}/download`, { responseType: 'blob', timeout: 600_000 })
export const favoriteReport = (id: string): Promise<ThinktankFavoriteResult> => request(http.post(`/thinktank/reports/${id}/favorite`))
export const unfavoriteReport = (id: string): Promise<ThinktankFavoriteResult> => request(http.delete(`/thinktank/reports/${id}/favorite`))
export const listReportLogs = (id: string, params?: LogPageParams): Promise<Page<KnowledgeOpLogItem>> =>
  request(http.get(`/thinktank/reports/${id}/logs`, { params }))
export const updateReport = (id: string, body: Partial<ReportItem> & { version: number }): Promise<ReportItem> =>
  request(http.patch(`/thinktank/reports/${id}`, body))
export const deleteReport = (id: string): Promise<{ deleted: boolean }> => request(http.delete(`/thinktank/reports/${id}`))
export const uploadReportFile = (file: File, metadata: ReportUploadMetadata = {}): Promise<ReportItem> =>
  postLibraryUpload('/thinktank/reports/upload', file, metadata)
export const uploadReportTags = (file: File, onProgress?: ProgressFn): Promise<ImportResult> =>
  postExcelImport('/thinktank/reports/upload-tags', file, onProgress, 180_000)
export const exportUndefinedReports = (): Promise<AxiosResponse<Blob>> =>
  http.get('/thinktank/reports/export-undefined', { responseType: 'blob', timeout: 600_000 })

/* 方案库（/thinktank/proposals） */
export const listProposals = (params: ProposalQuery): Promise<Page<ProposalItem>> => request(http.get('/thinktank/proposals', { params }))
export const previewProposal = (id: string): Promise<ProposalPreviewPayload> => request(http.get(`/thinktank/proposals/${id}/preview`))
export const fetchProposalContentBlob = (id: string, signal?: AbortSignal): Promise<AxiosResponse<Blob>> =>
  http.get(`/thinktank/proposals/${id}/content`, { responseType: 'blob', timeout: 600_000, signal })
export const downloadProposalBlob = (id: string): Promise<AxiosResponse<Blob>> =>
  http.get(`/thinktank/proposals/${id}/download`, { responseType: 'blob', timeout: 600_000 })
export const favoriteProposal = (id: string): Promise<ThinktankFavoriteResult> => request(http.post(`/thinktank/proposals/${id}/favorite`))
export const unfavoriteProposal = (id: string): Promise<ThinktankFavoriteResult> => request(http.delete(`/thinktank/proposals/${id}/favorite`))
export const listProposalLogs = (id: string, params?: LogPageParams): Promise<Page<KnowledgeOpLogItem>> =>
  request(http.get(`/thinktank/proposals/${id}/logs`, { params }))
export const updateProposal = (id: string, body: Partial<ProposalItem> & { version: number }): Promise<ProposalItem> =>
  request(http.patch(`/thinktank/proposals/${id}`, body))
export const deleteProposal = (id: string): Promise<{ deleted: boolean }> => request(http.delete(`/thinktank/proposals/${id}`))
export const uploadProposalFile = (file: File, metadata: ProposalUploadMetadata = {}): Promise<ProposalItem> =>
  postLibraryUpload('/thinktank/proposals/upload', file, metadata)
export const uploadProposalTags = (file: File, onProgress?: ProgressFn): Promise<ImportResult> =>
  postExcelImport('/thinktank/proposals/upload-tags', file, onProgress, 180_000)
export const exportUndefinedProposals = (): Promise<AxiosResponse<Blob>> =>
  http.get('/thinktank/proposals/export-undefined', { responseType: 'blob', timeout: 600_000 })

/* 我的收藏（/thinktank/favorites） */
export const listThinktankFavorites = (params: ThinktankFavoritesQuery = {}): Promise<ThinktankFavoritesResponse> =>
  request(http.get('/thinktank/favorites', { params }))
export const unfavoriteThinktankItem = (library: ThinktankLibraryKey, id: string): Promise<ThinktankFavoriteResult> =>
  request(http.delete(`/thinktank/${library}/${id}/favorite`))
export const downloadThinktankItemBlob = (library: ThinktankLibraryKey, id: string): Promise<AxiosResponse<Blob>> =>
  http.get(`/thinktank/${library}/${id}/download`, { responseType: 'blob', timeout: 600_000 })
