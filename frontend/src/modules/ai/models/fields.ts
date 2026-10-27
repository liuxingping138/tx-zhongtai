import type { ModelConfig, ModelConfigBody } from '@/api/ai'
import type { DataColumn } from '@/components/dataColumns'
import type { EditorGroup } from '@/components/editorGroups'
import type { RecordForm } from '@/composables/useRecordEditor'

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

export const TABLE_COLUMNS: DataColumn[] = [
  { prop: 'name', label: '显示名称', minWidth: 240, grow: 2 },
  { prop: 'enabled', label: '状态', width: 80 },
  { prop: 'id', label: '模型ID', width: 200 },
  { prop: 'provider', label: '厂商', width: 100 },
  { prop: 'endpoint', label: '接入点', width: 220 },
  { prop: 'web_search', label: '联网', width: 90 },
  { prop: 'service_tier', label: '服务档位', width: 120 },
  { prop: 'thinking', label: '深度思考', width: 110 },
  { prop: 'reasoning_effort', label: '思考强度', width: 110 },
  { prop: 'input_price', label: '常规输入', fullLabel: '常规输入单价（元/千 token）', width: 100 },
  { prop: 'output_price', label: '常规输出', fullLabel: '常规输出单价（元/千 token）', width: 100 },
  { prop: 'flex_input_price', label: '低优输入', fullLabel: '低优输入单价（元/千 token）', width: 100 },
  { prop: 'flex_output_price', label: '低优输出', fullLabel: '低优输出单价（元/千 token）', width: 100 },
  { prop: 'peak_input_price', label: '高峰输入', fullLabel: '高峰输入单价（元/千 token）', width: 100 },
  { prop: 'peak_output_price', label: '高峰输出', fullLabel: '高峰输出单价（元/千 token）', width: 100 },
  { prop: 'peak_hours', label: '高峰时段', width: 190 },
  { prop: 'search_price', label: '联网单价', fullLabel: '联网单价（元/次）', width: 100 },
  { prop: 'rate_limit', label: '限流', minWidth: 220, grow: 1 },
  { prop: 'sort_order', label: '排序', width: 80 },
  { prop: 'updated_at', label: '更新时间', width: 190, time: true },
  { prop: 'updated_by_name', label: '更新人', width: 110 },
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
          hint: '低优价格低、不保证速度；接入点不支持低优时选「不传」。',
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
      hint: '按调用时刻选价：低优档用低优价；填了高峰价的，工作日高峰时段用高峰价；其余用常规价。',
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
          hint: '北京时间周一到周五；填了高峰价、这里不填时按上面的默认时段。',
        },
        { key: 'search_price', label: '联网单价', maxLength: 20, hint: '元/次；不联网填 0。' },
      ],
    },
  ]
}

export const EDITOR_GROUPS = editorGroups(BASIC_FIELDS)
/** 编辑已有模型时模型ID只读：改了就和模板、历史任务对不上了。 */
export const EDIT_GROUPS = editorGroups(BASIC_FIELDS.map(field => (field.key === 'id' ? { ...field, disabled: true } : field)))
