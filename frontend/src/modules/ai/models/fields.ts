import type { ModelConfig, ModelConfigBody } from '@/api/ai'
import type { DataColumn } from '@/components/dataColumns'
import type { EditorGroup } from '@/components/editorGroups'
import type { FieldError, RecordForm } from '@/composables/useRecordEditor'

/** 枚举字段的代码值 ↔ 页面文字。空串表示不传这个参数。 */
const LABELS = {
  provider: { ark: '字节方舟', baidu: '百度千帆' },
  web_search: { true: '联网', false: '不联网' },
  thinking: { enabled: '开启', disabled: '关闭', switch: '提问时可选', '': '按模型默认' },
  reasoning_effort: { low: '低（low）', high: '高（high）', max: '最高（max）', '': '按模型默认' },
  service_tier: { flex: '低优（flex）', auto: '常规（auto）', '': '按模型默认' },
  enabled: { true: '启用', false: '停用' },
} as const satisfies Record<string, Record<string, string>>

type LabelKey = keyof typeof LABELS
const LABEL_KEYS = Object.keys(LABELS) as LabelKey[]

function choices(key: LabelKey): string[] {
  return Object.values(LABELS[key])
}

function codeOf(key: LabelKey, label: string): string {
  return Object.entries(LABELS[key]).find(([, text]) => text === label)?.[0] ?? ''
}

/** 列表和编辑抽屉都用这份：枚举换成中文，其余原样。 */
export type ModelRow = Omit<ModelConfig, LabelKey | 'sort_order'> & Record<LabelKey, string> & { sort_order: string }

export function toRow(item: ModelConfig): ModelRow {
  const labels = Object.fromEntries(
    LABEL_KEYS.map(key => [key, (LABELS[key] as Record<string, string>)[String(item[key])] ?? String(item[key])]),
  ) as Record<LabelKey, string>
  return { ...item, ...labels, sort_order: String(item.sort_order) }
}

export function toBody(form: RecordForm): ModelConfigBody {
  const text = (key: string) => (form[key] ?? '').trim()
  return {
    id: text('id'),
    name: text('name'),
    provider: codeOf('provider', text('provider')),
    endpoint: text('endpoint'),
    web_search: codeOf('web_search', text('web_search')) === 'true',
    thinking: codeOf('thinking', text('thinking')),
    reasoning_effort: codeOf('reasoning_effort', text('reasoning_effort')),
    service_tier: codeOf('service_tier', text('service_tier')),
    input_price: text('input_price'),
    output_price: text('output_price'),
    flex_input_price: text('flex_input_price'),
    flex_output_price: text('flex_output_price'),
    peak_input_price: text('peak_input_price'),
    peak_output_price: text('peak_output_price'),
    peak_hours: text('peak_hours'),
    cache_price: text('cache_price'),
    peak_cache_price: text('peak_cache_price'),
    search_price: text('search_price'),
    rate_limit: text('rate_limit'),
    enabled: codeOf('enabled', text('enabled')) !== 'false',
    sort_order: Number(text('sort_order')) || 0,
  }
}

/** 新增时的预填：方舟、开思考、低思考强度，和现有模型一致。 */
export const CREATE_DEFAULTS: RecordForm = {
  provider: LABELS.provider.ark,
  web_search: LABELS.web_search.false,
  thinking: LABELS.thinking.enabled,
  reasoning_effort: LABELS.reasoning_effort.low,
  service_tier: LABELS.service_tier[''],
  enabled: LABELS.enabled.true,
  search_price: '0',
  sort_order: '100',
}

const PRICE_HINT = '元/千 token'

export const TOKEN_PRICE_KEYS = [
  'input_price',
  'output_price',
  'flex_input_price',
  'flex_output_price',
  'peak_input_price',
  'peak_output_price',
  'cache_price',
  'peak_cache_price',
] as const

const TOKEN_PRICE_SET = new Set<string>(TOKEN_PRICE_KEYS)
const DECIMAL_RE = /^\d+(?:\.\d{1,6})?$/

export function toMillionYuan(raw: string): string {
  const trimmed = raw.trim()
  if (!DECIMAL_RE.test(trimmed)) return ''
  const num = Number(trimmed)
  if (!Number.isFinite(num) || num < 0 || num >= 1000) return ''
  return `¥${Number((num * 1000).toFixed(6))}`
}

export function priceCellTitle(raw: string): string {
  const million = toMillionYuan(raw)
  return million ? `${raw} 元/千 token（即 ${million} / 百万 token）` : raw
}

/** 编辑抽屉：在原有灰字说明位置安静附注折合每百万 token 单价，不加彩色胶囊、不折叠任何字段。 */
export function withLivePriceHints(groups: EditorGroup[], form: RecordForm): EditorGroup[] {
  return groups.map(group => ({
    ...group,
    fields: group.fields.map((field) => {
      if (!TOKEN_PRICE_SET.has(field.key) || !field.hint) return field
      const million = toMillionYuan(form[field.key] ?? '')
      if (!million) return field
      return { ...field, hint: field.hint.replace(PRICE_HINT, `${PRICE_HINT}（即 ${million} / 百万 token）`) }
    }),
  }))
}

/** 详情抽屉底部的轻量折算附注，一眼对照百万 token 口径。 */
export function formatMillionSummary(row: ModelRow): string {
  const parts: string[] = []
  const regIn = toMillionYuan(row.input_price)
  const regOut = toMillionYuan(row.output_price)
  if (regIn && regOut) parts.push(`常规 ${regIn} / ${regOut}`)
  const flexIn = toMillionYuan(row.flex_input_price)
  const flexOut = toMillionYuan(row.flex_output_price)
  if (flexIn && flexOut) parts.push(`低优 ${flexIn} / ${flexOut}`)
  const peakIn = toMillionYuan(row.peak_input_price)
  const peakOut = toMillionYuan(row.peak_output_price)
  if (peakIn && peakOut) parts.push(`高峰 ${peakIn} / ${peakOut}`)
  const cache = toMillionYuan(row.cache_price)
  const peakCache = toMillionYuan(row.peak_cache_price)
  if (cache) parts.push(peakCache ? `缓存 ${cache}（高峰 ${peakCache}）` : `缓存 ${cache}`)
  return parts.length ? `折合每百万 token（输入 / 输出）：${parts.join(' · ')}` : ''
}

/** 保存前成对单价校验，错误直接落在对应输入框下方。 */
export function checkModelForm(form: RecordForm): FieldError | undefined {
  const has = (key: string) => Boolean((form[key] ?? '').trim())
  if (has('flex_input_price') !== has('flex_output_price')) {
    return { key: has('flex_input_price') ? 'flex_output_price' : 'flex_input_price', message: '低优输入、输出单价要一起填或都不填' }
  }
  if (codeOf('service_tier', (form.service_tier ?? '').trim()) === 'flex' && !has('flex_input_price')) {
    return { key: 'flex_input_price', message: '服务档位选了低优，要填低优单价' }
  }
  if (has('peak_input_price') !== has('peak_output_price')) {
    return { key: has('peak_input_price') ? 'peak_output_price' : 'peak_input_price', message: '高峰输入、输出单价要一起填或都不填' }
  }
  if (has('peak_cache_price') && !has('cache_price')) {
    return { key: 'cache_price', message: '填了高峰缓存单价，也要填平时的缓存单价' }
  }
  return undefined
}

export const TABLE_COLUMNS: DataColumn[] = [
  // 显示名称写全（2026-11-03 用户：最起码名称要显示全），最长的「字节-DeepSeek-V4.1-Flash经济版（不联网）」约 318px
  { prop: 'name', label: '显示名称', minWidth: 318, grow: 2 },
  // 状态是行内开关，和用户管理、任务调度同一种（ModelList 的 #cell-enabled）
  { prop: 'enabled', label: '状态', width: 100 },
  { prop: 'provider', label: '厂商', width: 92, tags: { 字节方舟: 'primary', 百度千帆: 'success' } },
  { prop: 'web_search', label: '联网', width: 80, tags: { 联网: 'success', 不联网: 'info' } },
  { prop: 'service_tier', label: '服务档位', width: 112, tags: { '低优（flex）': 'warning', '常规（auto）': 'primary', 按模型默认: 'info' } },
  { prop: 'input_price', label: '常规输入', fullLabel: '常规输入单价', width: 92 },
  { prop: 'output_price', label: '常规输出', fullLabel: '常规输出单价', width: 92 },
  { prop: 'flex_input_price', label: '低优输入', fullLabel: '低优输入单价', width: 92 },
  { prop: 'flex_output_price', label: '低优输出', fullLabel: '低优输出单价', width: 92 },
  { prop: 'peak_input_price', label: '高峰输入', fullLabel: '高峰输入单价', width: 92 },
  { prop: 'peak_output_price', label: '高峰输出', fullLabel: '高峰输出单价', width: 92 },
  { prop: 'cache_price', label: '缓存单价', fullLabel: '缓存单价', width: 92 },
  { prop: 'peak_cache_price', label: '高峰缓存', fullLabel: '高峰缓存单价', width: 92 },
  { prop: 'peak_hours', label: '高峰时段', width: 180 },
  { prop: 'search_price', label: '联网单价', fullLabel: '联网单价', width: 92 },
  { prop: 'thinking', label: '深度思考', width: 100 },
  { prop: 'reasoning_effort', label: '思考强度', width: 100 },
  { prop: 'rate_limit', label: '限流', fullLabel: '限流说明', minWidth: 200, grow: 1 },
  { prop: 'sort_order', label: '排序', width: 72 },
  // 模型ID、接入点这类技术标识按 DESIGN.md 放在最后、留痕列之前，首屏直接看到名称、状态、档位与价格。
  { prop: 'id', label: '模型ID', width: 190 },
  { prop: 'endpoint', label: '接入点', width: 210 },
  { prop: 'updated_at', label: '更新时间', width: 180, time: true },
  { prop: 'updated_by_name', label: '更新人', width: 100 },
]

/** 首屏默认勾选的核心常用列（1440px 零横向滚动）；其余列随时可在「列设置」中勾选或一键「显示全部列」。 */
export const DEFAULT_SELECTED_COLUMNS = [
  'name',
  'enabled',
  'provider',
  'web_search',
  'service_tier',
  'input_price',
  'output_price',
  'cache_price',
  'sort_order',
]

export const SUMMARY_KEYS = ['name', 'enabled', 'service_tier', 'input_price']

const BASIC_FIELDS: EditorGroup['fields'] = [
  { key: 'id', label: '模型ID', required: true, maxLength: 64, hint: '模板和批量任务按它引用，建好后不能改。' },
  { key: 'name', label: '显示名称', required: true, maxLength: 100 },
  { key: 'provider', label: '厂商', required: true, choices: choices('provider') },
  {
    key: 'endpoint',
    label: '接入点',
    required: true,
    maxLength: 128,
    hint: '方舟填 ep- 开头的接入点 ID，千帆填模型名。密钥按厂商配置在服务器上，不在这里填。',
  },
  { key: 'enabled', label: '状态', required: true, choices: choices('enabled'), hint: '停用后不再出现在模型下拉里，已排队的任务照常跑完。' },
  { key: 'sort_order', label: '排序', maxLength: 6, hint: '数字越小越靠前。' },
]

function editorGroups(basic: EditorGroup['fields']): EditorGroup[] {
  return [
    { title: '基础信息', hint: '模型在页面上的名称和调用地址。', fields: basic },
    {
      title: '调用参数',
      hint: '每次提问原样带上这些参数，保存后立即生效。',
      fields: [
        { key: 'web_search', label: '联网搜索', required: true, choices: choices('web_search') },
        {
          key: 'service_tier',
          label: '服务档位',
          required: true,
          choices: choices('service_tier'),
          hint: '低优价格低、不保证速度；接入点不支持低优时选「按模型默认」。',
        },
        {
          key: 'thinking',
          label: '深度思考',
          required: true,
          choices: choices('thinking'),
          hint: '「提问时可选」由页面上的思考开关决定（千帆）。',
        },
        { key: 'reasoning_effort', label: '思考强度', required: true, choices: choices('reasoning_effort'), hint: '越低思考越浅、输出越省。' },
        { key: 'rate_limit', label: '限流说明', long: true, maxLength: 500, hint: '只做记录，不控制批量并发。' },
      ],
    },
    {
      title: '价格',
      hint: '单位：元/千 token（联网单价为元/次）。按调用时刻选价：低优档用低优价；填了高峰价的，工作日高峰时段用高峰价；其余用常规价。命中上下文缓存的输入按缓存单价算，不分低优、常规档。',
      fields: [
        { key: 'input_price', label: '常规输入单价', required: true, maxLength: 20, hint: PRICE_HINT },
        { key: 'output_price', label: '常规输出单价', required: true, maxLength: 20, hint: PRICE_HINT },
        { key: 'flex_input_price', label: '低优输入单价', maxLength: 20, hint: `${PRICE_HINT}；不支持低优就不填。` },
        { key: 'flex_output_price', label: '低优输出单价', maxLength: 20, hint: PRICE_HINT },
        { key: 'peak_input_price', label: '高峰输入单价', maxLength: 20, hint: `${PRICE_HINT}；不分时段就不填，此时常规价即空闲价。` },
        { key: 'peak_output_price', label: '高峰输出单价', maxLength: 20, hint: PRICE_HINT },
        {
          key: 'peak_hours',
          label: '高峰时段',
          maxLength: 100,
          placeholder: '09:00-12:00,14:00-18:00',
          hint: '北京时间周一到周五；填了高峰价或高峰缓存单价、这里不填时按上面的默认时段。',
        },
        {
          key: 'cache_price',
          label: '缓存单价',
          maxLength: 20,
          hint: `${PRICE_HINT}；命中上下文缓存的输入按这个价算。不填时缓存部分按输入单价算。`,
        },
        {
          key: 'peak_cache_price',
          label: '高峰缓存单价',
          maxLength: 20,
          hint: `${PRICE_HINT}；缓存也分时段计价的才填，工作日高峰时段用它，要先填缓存单价。`,
        },
        { key: 'search_price', label: '联网单价', maxLength: 20, hint: '元/次；不联网填 0。' },
      ],
    },
  ]
}

export const EDITOR_GROUPS = editorGroups(BASIC_FIELDS)
/** 编辑已有模型时模型ID只读：改了就和模板、历史任务对不上了。 */
export const EDIT_GROUPS = editorGroups(BASIC_FIELDS.map(field => (field.key === 'id' ? { ...field, disabled: true } : field)))
