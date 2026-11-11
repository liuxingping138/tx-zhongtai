import type { CrawlerProvince } from '@/api/crawlerMonitoring'

export function percent(part: number, total: number): string {
  return total ? `${((part / total) * 100).toFixed(1)}%` : '0%'
}

/** 按网站总数从多到少，同数再按停更数；全部分类都保留，网站少的也不剔除：全国、国央企和 31 个省是同一套「省份」字段分类。 */
export function sortProvinces(items: CrawlerProvince[], limit?: number): CrawlerProvince[] {
  const sorted = [...items].sort((a, b) => b.sites - a.sites || b.stale - a.stale || a.name.localeCompare(b.name, 'zh'))
  return limit ? sorted.slice(0, limit) : sorted
}

export interface ProvinceTile {
  item: CrawlerProvince
  /** 「共 466 个 · 停更 89%」；没有网站时写「暂无网站」 */
  caption: string
  /** 比例条三段宽度（百分比），没有网站时全为 0 */
  shares: { normal: number; watch: number; stale: number }
  /** 悬停提示：各状态数量和合并前的写法 */
  hint: string
}

function rawNamesHint(item: CrawlerProvince): string {
  return item.raw_names.length > 1 ? `含写法：${item.raw_names.map(name => name || '空').join('、')}` : ''
}

export function provinceTile(item: CrawlerProvince): ProvinceTile {
  const share = (value: number) => (item.sites ? (value / item.sites) * 100 : 0)
  return {
    item,
    caption: item.sites ? `共 ${item.sites.toLocaleString()} 个 · 停更 ${percent(item.stale, item.sites)}` : '暂无网站',
    shares: { normal: share(item.normal), watch: share(item.watch), stale: share(item.stale) },
    hint: [`正常 ${item.normal}　关注 ${item.watch}　停更 ${item.stale}`, rawNamesHint(item)].filter(Boolean).join('\n'),
  }
}

/** 下方明细已按这个分类的全部原始写法筛选时，排行行和卡片显示为选中。 */
export function provinceSelected(item: CrawlerProvince, applied: string[]): boolean {
  return applied.length > 0 && [...applied].sort().join('|') === [...item.raw_names].sort().join('|')
}

/** 简称用于紧凑视图展示；全国、国央企等原样，完整名称在提示框里。 */
export function provinceShortName(name: string): string {
  return name.replace(/(壮族|回族|维吾尔)?自治区$|特别行政区$|[省市]$/, '') || name
}

/** 双列水平排行行模型：左名、中段蓝红比例轨、右对齐总数与停更徽标。 */
export interface ProvinceRankRow {
  rank: number
  shortName: string
  item: CrawlerProvince
  okWidth: number
  staleWidth: number
  staleRate: number
  hint: string
}

export function provinceRanks(items: CrawlerProvince[]): ProvinceRankRow[] {
  const maxSites = Math.max(...items.map(item => item.sites), 1)
  return items.map((item, index) => {
    const okCount = Math.max(0, item.sites - item.stale)
    const staleRate = item.sites ? Math.round((item.stale / item.sites) * 100) : 0
    const hint = item.sites
      ? [
          `${item.name}（共 ${item.sites.toLocaleString()} 个）`,
          `正常 ${item.normal}　关注 ${item.watch}　停更 ${item.stale}（停更率 ${percent(item.stale, item.sites)}）`,
          rawNamesHint(item),
        ].filter(Boolean).join('\n')
      : `${item.name}：暂无网站`
    return {
      rank: index + 1,
      shortName: provinceShortName(item.name),
      item,
      okWidth: (okCount / maxSites) * 100,
      staleWidth: (item.stale / maxSites) * 100,
      staleRate,
      hint,
    }
  })
}
