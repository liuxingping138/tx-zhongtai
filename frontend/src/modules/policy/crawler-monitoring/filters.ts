import type { HealthStatus } from '@/api/crawlerMonitoring'

export const STATUS_BY_LABEL: Record<string, HealthStatus> = {
  正常: 'normal', 观察: 'watch', 断爬: 'broken', 从未出数: 'never',
}

/** 列表与导出共用 API 值，URL/控件仍保留中文显示值。 */
export function crawlerFilters(query: Record<string, unknown>) {
  return {
    province_name: String(query.province_name || '') || undefined,
    city_name: String(query.city_name || '') || undefined,
    site_name: String(query.site_name || '') || undefined,
    tag: String(query.tag || '') || undefined,
    health_status: STATUS_BY_LABEL[String(query.health_status)] || undefined,
  }
}
