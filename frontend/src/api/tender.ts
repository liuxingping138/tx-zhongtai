import { http, request } from './http'

export type TenderKind = 'purchaser' | 'winbid'
export interface TenderRecord {
  id: string
  project_content_id: string | null
  project_name: string | null
  project_status: string
  is_supp_scene: number
  [key: string]: string | number | null
}
export interface TenderPoint {
  date?: string
  province?: string
  purchaser: number
  winbid: number
  tagged: number
  enriched: number
  scenario: number
  purchaser_passed?: number
  winbid_passed?: number
}
export interface TenderStatistics {
  date_from: string
  date_to: string
  as_of: string
  daily: TenderPoint[]
  provinces: TenderPoint[]
}
export interface CountJob<T> { state: 'pending' | 'ready' | 'error'; data: T | null; message: string }
export interface TenderPage { items: TenderRecord[]; has_more: boolean; page: number; page_size: number }
export interface TenderTotals { total: number; purchaser: number; winbid: number; as_of: string }

export function listTenderRecords(kind: TenderKind, params: Record<string, unknown>): Promise<TenderPage> {
  const clean = Object.fromEntries(Object.entries(params).filter(([, value]) => value !== '' && value !== null))
  return request(http.get(`/tender/${kind}`, { params: clean, timeout: 60_000 }))
}
export function getTenderRecord(kind: TenderKind, id: string, status: string): Promise<TenderRecord> {
  return request(http.get(`/tender/${kind}/${id}`, { params: { project_status: status } }))
}
export function getTenderContent(kind: TenderKind, id: string, status: string): Promise<{ html: string }> {
  return request(http.get(`/tender/${kind}/${id}/content`, { params: { project_status: status } }))
}
export function getTenderStatistics(dateFrom: string, dateTo: string): Promise<TenderStatistics> {
  return request(http.get('/tender/statistics', { params: { date_from: dateFrom, date_to: dateTo }, timeout: 120_000 }))
}
export function getTenderTotals(): Promise<CountJob<TenderTotals>> {
  return request(http.get('/tender/statistics/totals', { timeout: 60_000 }))
}

export function getTenderCount(kind: TenderKind, params: Record<string, unknown>): Promise<CountJob<{ total: number }>> {
  const clean = Object.fromEntries(Object.entries(params).filter(([, value]) => value !== '' && value !== null))
  return request(http.get(`/tender/${kind}/count`, { params: clean }))
}
