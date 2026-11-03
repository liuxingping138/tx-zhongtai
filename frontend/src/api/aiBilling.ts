import { http, request } from './http'

/** 一天里一个模型、一种用途的花费。用途：批量任务、样本试跑、试发、多轮对话（已下线，只剩历史记录），或定时任务的发起方（如「政策AI打标·类型判断」）。 */
export interface BillingRow {
  day: string
  model: string
  purpose: string
  calls: number
  input_tokens: number
  output_tokens: number
  cost: string
}

export interface AiBilling {
  date_from: string
  date_to: string
  items: BillingRow[]
}

/** 北京日期，含首尾，最多 366 天。 */
export const getAiBilling = (dateFrom: string, dateTo: string) =>
  request<AiBilling>(http.get('/ai/billing', { params: { date_from: dateFrom, date_to: dateTo } }))
