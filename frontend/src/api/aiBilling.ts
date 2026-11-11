import { http, request } from './http'

/** 一天里一个模型、一种用途的花费。三级归属：
 * scene 业务分类（日常调度 = 定时任务；测试 = 页面上的批量任务、样本试跑、试发、已下线的多轮对话）→
 * category 一级业务板块（政策 / 客户 / 招投标，取模板类型）→
 * purpose 二级业务板块（原来的「用途」：批量任务、样本试跑、试发、多轮对话，或定时任务的发起方如「政策AI打标·类型判断」）。 */
export interface BillingRow {
  day: string
  model: string
  scene: string
  category: string
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
