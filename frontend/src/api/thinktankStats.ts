import type { AxiosResponse } from 'axios'

import { http, request } from './http'

export type ThinktankStatsLibrary = 'all' | 'knowledge' | 'reports' | 'proposals'
export type ThinktankStatsSubLibrary = 'knowledge' | 'reports' | 'proposals'
export type ThinktankStatsGranularity = 'day' | 'week' | 'month' | 'quarter' | 'year'
export type ThinktankStatsPreset = '7d' | '30d' | 'quarter' | 'year' | 'all'

export interface ThinktankStatsQuery {
  library?: ThinktankStatsLibrary
  granularity?: ThinktankStatsGranularity
  preset?: ThinktankStatsPreset
  date_from?: string
  date_to?: string
}

export interface LibraryBreakdown {
  key: ThinktankStatsSubLibrary
  label: string
  files: number
  defined: number
  defined_rate: number
  share_pct: number
  size_bytes: number
  size_display: string
}

export interface AssetsSummary {
  total_files: number
  defined_files: number
  undefined_files: number
  defined_rate: number
  total_size_bytes: number
  total_size_display: string
  libraries: LibraryBreakdown[]
}

export interface BehaviorSummary {
  uploads: number
  uploads_delta_pct: number | null
  governance: number
  previews: number
  previews_delta_pct: number | null
  downloads: number
  downloads_delta_pct: number | null
  favorites_net: number
  favorites_added: number
  active_users: number
  active_users_delta_pct: number | null
}

export interface DimensionItem {
  name: string
  count: number
  share_pct: number
}

export interface DimensionGroup {
  key: string
  label: string
  note: string
  show_win_banner: boolean
  drill_field: string
  total: number
  items: DimensionItem[]
}

export interface ProposalWinSummary {
  total: number
  won: number
  lost: number
  pending: number
  aborted: number
  win_rate: number
  win_amount_wan: number
}

export interface TrendPoint {
  bucket_key: string
  label: string
  knowledge_uploads: number
  reports_uploads: number
  proposals_uploads: number
  total_uploads: number
  governance: number
  previews: number
  downloads: number
  active_users: number
}

export interface RankedDocItem {
  id: string
  library: ThinktankStatsSubLibrary
  library_label: string
  title: string
  category: string
  industry: string
  dept: string
  file_suffix: string
  file_size_bytes: number
  file_size_display: string
  uploader: string
  uploaded_at: string
  is_defined: boolean
  downloads: number
  previews: number
  favorites: number
}

export interface RankedActorItem {
  actor_id: string
  name: string
  uploads: number
  governance: number
  previews: number
  downloads: number
  active_days: number
}

export interface RankedDeptItem {
  name: string
  files: number
  defined: number
  defined_rate: number
}

export interface ThinktankStatisticsPayload {
  as_of: string
  library: ThinktankStatsLibrary
  granularity: ThinktankStatsGranularity
  window: {
    preset: string
    date_from: string | null
    date_to: string
    days: number
  }
  assets: AssetsSummary
  behavior: BehaviorSummary
  dimensions: DimensionGroup[]
  proposal_win: ProposalWinSummary | null
  trend: TrendPoint[]
  top_documents: {
    download: RankedDocItem[]
    preview: RankedDocItem[]
    favorite: RankedDocItem[]
  }
  top_contributors: {
    upload: RankedActorItem[]
    active: RankedActorItem[]
    dept: RankedDeptItem[]
  }
}

export interface DocPeekPayload {
  document: RankedDocItem
  recent_logs: {
    actor_name: string
    op_type: string
    detail: string
    created_at: string
  }[]
}

export const getThinktankStatistics = (params: ThinktankStatsQuery = {}): Promise<ThinktankStatisticsPayload> =>
  request(http.get('/thinktank/statistics', { params }))

export const getThinktankDocPeek = (
  library: ThinktankStatsSubLibrary,
  fileId: string,
): Promise<DocPeekPayload> =>
  request(http.get(`/thinktank/statistics/documents/${library}/${fileId}`))

export const exportThinktankStatisticsBlob = (
  params: ThinktankStatsQuery = {},
): Promise<AxiosResponse<Blob>> =>
  http.get('/thinktank/statistics/export', { params, responseType: 'blob', timeout: 120_000 })
