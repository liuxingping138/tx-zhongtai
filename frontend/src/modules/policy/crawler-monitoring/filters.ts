import type { HealthStatus } from '@/api/crawlerMonitoring'
import { filterList } from '@/composables/useListQuery'

export const STATUS_BY_LABEL: Record<string, HealthStatus> = {
  正常: 'normal', 观察: 'watch', 断爬: 'broken', 从未出数: 'never',
}

function orUndefined<T>(values: T[]): T[] | undefined {
  return values.length ? values : undefined
}

/** 控件里是中文状态名，接口要英文枚举；未知名称直接丢掉，不发给后端。 */
export function statusValues(value: unknown): HealthStatus[] {
  return filterList(value).map(label => STATUS_BY_LABEL[label]).filter((status): status is HealthStatus => !!status)
}

/** 列表与导出共用 API 值，URL/控件仍保留中文显示值。 */
export function crawlerFilters(query: Record<string, unknown>) {
  return {
    province_name: orUndefined(filterList(query.province_name)),
    city_name: orUndefined(filterList(query.city_name)),
    site_name: orUndefined(filterList(query.site_name)),
    tag: orUndefined(filterList(query.tag)),
    health_status: orUndefined(statusValues(query.health_status)),
  }
}
