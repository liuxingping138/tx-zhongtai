import type { SiteStatus } from '@/api/crawlerMonitoring'
import { filterList } from '@/composables/useListQuery'

export const STATUS_BY_LABEL: Record<string, SiteStatus> = { 正常: 'normal', 关注: 'watch', 停更: 'stale' }

function orUndefined<T>(values: T[]): T[] | undefined {
  return values.length ? values : undefined
}

/** 控件里是中文状态名，接口要英文枚举；未知名称直接丢掉，不发给后端。 */
export function statusValues(value: unknown): SiteStatus[] {
  return filterList(value).map(label => STATUS_BY_LABEL[label]).filter((status): status is SiteStatus => !!status)
}

/** 列表与导出共用 API 值，URL/控件仍保留中文显示值。 */
export function siteFilters(query: Record<string, unknown>) {
  return {
    province_name: orUndefined(filterList(query.province_name)),
    city_name: orUndefined(filterList(query.city_name)),
    site_name: orUndefined(filterList(query.site_name)),
    status: orUndefined(statusValues(query.status)),
  }
}

/** 卡片里的大数用「万/亿」缩写，完整值放在 title 里。 */
export function compactCount(value: number): string {
  if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(2)} 亿`
  if (value >= 10_000) return `${(value / 10_000).toFixed(1)} 万`
  return value.toLocaleString()
}
