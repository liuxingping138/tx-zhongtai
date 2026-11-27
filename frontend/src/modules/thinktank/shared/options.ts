/** 智库 6 张专属码表的兜底枚举与通用标签/选项工具（优先采用后端 `/options` 返回值，不可用时平滑回退）。 */

export const FILE_TYPE_FALLBACK = [
  '经分', '通报', '工作会', '行业营销指引', '工作部署&专项行动', '网络规划',
  '考核', '产品', '政企改革&数字化', '客户视图', '通知', '渠道&生态', '国际业务', '其他',
] as const

export const DEPARTMENT_FALLBACK = [
  '政企部', '市场部', '工业行业事业部', '公众客户销售中心', '国际部',
  '集团商业客户拓展部', '集团政企应急行业事业部', '交通物流行业事业部', '柯瑞文董事长',
] as const

export const INDUSTRY_FALLBACK = [
  '党政', '工业能源', '教育', '医卫', '交通物流', 'IT互联网',
  '金融', '农业', '住建', '文旅', '中小', '无',
] as const

export const PRODUCT_TYPE_FALLBACK = [
  '云', '网', '数', '智', '安', '语音', '消息', '数字平台', '量子', '解决方案', '服务', '无',
] as const

export const PROVINCE_FALLBACK = [
  '集团', '北京市', '天津市', '河北省', '山西省', '内蒙古自治区', '辽宁省', '吉林省', '黑龙江省',
  '上海市', '江苏省', '浙江省', '安徽省', '福建省', '江西省', '山东省', '河南省', '湖北省', '湖南省',
  '广东省', '广西壮族自治区', '海南省', '重庆市', '四川省', '贵州省', '云南省', '西藏自治区',
  '陕西省', '甘肃省', '青海省', '宁夏回族自治区', '新疆维吾尔自治区',
] as const

export const MARKET_CATEGORY_FALLBACK = ['行客', '商客', '综合', '无'] as const

export const YES_NO_OPTIONS = ['是', '否'] as const
export const PROPOSAL_RESULT_OPTIONS = ['中标', '未中标', '待定', '流标'] as const
export const TAG_STATUS_OPTIONS = ['已定义', '未定义'] as const

export const UPLOAD_ACCEPT = '.pdf,.xlsx,.xls,.docx,.doc,.pptx,.ppt,.txt,.csv,.md'

function dedupe(items: readonly string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of items) {
    const val = raw.trim()
    if (val && !seen.has(val)) {
      seen.add(val)
      out.push(val)
    }
  }
  return out
}

/** 优先使用后端动态 `/options`（来源于智库专属码表），为空时平滑回退内置兜底列表。 */
export function preferOptions(dynamic?: readonly string[] | null, fallback: readonly string[] = []): string[] {
  const cleaned = dynamic ? dedupe(dynamic) : []
  return cleaned.length > 0 ? cleaned : dedupe(fallback)
}

/** 结合权限可编辑范围裁剪动态选项；范围未传时保留完整列表。 */
export function scopedOptions(
  dynamic: readonly string[] | undefined,
  fallback: readonly string[],
  allowed?: readonly string[] | null,
  exclude?: readonly string[],
): string[] {
  const excluded = new Set(exclude ?? [])
  const base = preferOptions(dynamic, fallback).filter(v => !excluded.has(v))
  if (!allowed) return base
  const allowSet = new Set(allowed)
  return base.filter(v => allowSet.has(v))
}

export function splitPipeTags(raw: string | undefined | null): string[] {
  if (!raw) return []
  return raw.split('|').map(s => s.trim()).filter(Boolean)
}

export function joinPipeTags(items: readonly string[]): string {
  return items.map(s => s.trim()).filter(Boolean).join('|')
}

export function displayCategory(value: string | undefined | null): string {
  return value && value.trim() ? value : '未定义'
}

export function suffixTagType(suffix: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  const s = (suffix || '').toUpperCase()
  if (s === 'PDF') return 'danger'
  if (s === 'PPT') return 'warning'
  if (s === 'EXCEL') return 'success'
  return 'info'
}

export function parseContentDispositionFilename(header: string | undefined, fallback: string): string {
  if (!header) return fallback
  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1].trim())
    } catch {
      return fallback
    }
  }
  const plainMatch = header.match(/filename="?([^";]+)"?/i)
  return plainMatch?.[1]?.trim() || fallback
}

export function joinWhoWhen(
  who: string | undefined,
  when: string | undefined,
  formatTimeFn: (val: string) => string,
): string {
  const parts = [who ? who.trim() : '', when ? formatTimeFn(when) : ''].filter(Boolean)
  return parts.length ? parts.join(' · ') : '—'
}
