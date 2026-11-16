import type { DataColumn } from '@/components/dataColumns'
import type { EditorGroup } from '@/components/editorGroups'

export const TABLE_COLUMNS: DataColumn[] = [
  { prop: 'policy_name', label: '政策名称', minWidth: 320, grow: 2 },
  // 后端按备注里的失败说明和三步的完成时间算出来的，只读，不进 Excel；和「打标状态」筛选同一套条件。
  { prop: 'ai_status', label: '打标状态', width: 130 },
  { prop: '是否政策', label: '是否政策', width: 96 },
  { prop: 'policy_types', label: '政策类型', minWidth: 200, grow: 1, wrap: true },
  { prop: '是否信息化政策', label: '是否信息化政策', width: 128 },
  { prop: '信息化标签', label: '信息化标签', minWidth: 160, wrap: true },
  { prop: '判定简因', label: '判定简因', minWidth: 220, wrap: true },
  { prop: 'issuing_dept', label: '出台部门', width: 220 },
  { prop: 'issuer_industry', label: '发文机构行业', minWidth: 140 },
  { prop: 'policy_level', label: '政策层级', width: 110 },
  { prop: 'province_name', label: '省份名称', width: 110 },
  { prop: 'city_name', label: '地市名称', width: 110 },
  { prop: 'issued_at', label: '出台日期', fullLabel: '当前政策出台时间', width: 140 },
  { prop: 'source_url', label: '原始网站链接', minWidth: 240, link: true },
  { prop: 'is_penetrate', label: '是否穿透', width: 100 },
  { prop: 'penetrate_words', label: '穿透词', minWidth: 180 },
  { prop: 'penetrate_score', label: '穿透词评分', width: 110 },
  { prop: 'need_interpret', label: '是否解读', width: 100 },
  { prop: 'remark', label: '备注', minWidth: 160 },
  // 编码对人没意义，放在名称后面的最后（2026-11-03：原来「省份编码」排在「省份名称」前面，列表里先看到 00、14）
  { prop: 'province_code', label: '省份编码', width: 100 },
  { prop: 'city_code', label: '地市编码', width: 100 },
  { prop: 'created_at', label: '入库时间', width: 190, time: true },
  { prop: 'created_by_name', label: '入库人', width: 110 },
  { prop: 'updated_at', label: '更新时间', width: 190, time: true },
  { prop: 'updated_by_name', label: '操作人', width: 110 },
]

/** 窄屏卡片的摘要字段，也是列设置早期「精简默认列」的识别依据。 */
export const SUMMARY_KEYS = ['policy_name', 'province_name', 'policy_types', '是否信息化政策', 'issued_at', 'need_interpret']

/** 列表的筛选字段，和列表页 query 里的一致；核对页靠它从地址栏带上筛选，翻上一条、下一条。 */
export const FILTER_KEYS = ['policy_name', 'province_name', 'policy_types', 'is_policy', 'is_info_policy', 'is_penetrate', 'need_interpret', 'ai_status']

export const EDITOR_GROUPS: EditorGroup[] = [
  {
    title: '政策基础信息',
    hint: '政策名称为必填项，其余信息按原文填写。',
    fields: [
      { key: 'policy_name', label: '政策名称', required: true, long: true },
      { key: 'issuing_dept', label: '出台部门', maxLength: 255 },
      { key: 'issuer_industry', label: '发文机构行业', maxLength: 255 },
      { key: 'policy_level', label: '政策层级', maxLength: 64 },
      { key: 'issued_at', label: '出台时间', placeholder: '如：2026-09-18', maxLength: 64 },
      { key: 'source_url', label: '原始网站链接', long: true, placeholder: 'https://' },
    ],
  },
  {
    title: '所属地区',
    hint: '地区名称和编码应与省市区码表保持一致。',
    fields: [
      { key: 'province_name', label: '省份名称', maxLength: 64 },
      { key: 'province_code', label: '省份编码', maxLength: 16 },
      { key: 'city_name', label: '地市名称', maxLength: 64 },
      { key: 'city_code', label: '地市编码', maxLength: 16 },
    ],
  },
  {
    title: '业务标签',
    hint: '填写政策分类、AI判定标签、穿透和解读信息，便于后续筛选。',
    fields: [
      { key: '是否政策', label: '是否政策', choices: ['是', '否', '疑似'] },
      { key: 'policy_types', label: '政策类型' },
      { key: '是否信息化政策', label: '是否信息化政策', choices: ['是', '否'] },
      { key: '信息化标签', label: '信息化标签', maxLength: 255 },
      { key: '判定简因', label: '判定简因', long: true },
      { key: 'is_penetrate', label: '是否穿透', maxLength: 32 },
      { key: 'need_interpret', label: '是否解读', maxLength: 64 },
      { key: 'penetrate_score', label: '穿透词评分', maxLength: 64 },
      { key: 'penetrate_words', label: '穿透词', long: true },
      { key: 'remark', label: '备注', long: true },
    ],
  },
]

const CORE_BASE_TAG_KEYS = new Set([
  'policy_name', 'issuing_dept', 'issuer_industry', 'policy_level',
  'province_code', 'province_name', 'city_code', 'city_name',
  'issued_at', 'policy_types', 'source_url', 'is_penetrate',
  'penetrate_words', 'penetrate_score', 'need_interpret', 'remark',
])

/** 拆分基础列与模板动态扩展列，供核对页保存提交。 */
export function packBaseTagPatch(form: Record<string, string>, version: number) {
  const core: Record<string, string> = {}
  const ai_outputs: Record<string, string> = {}
  for (const [key, val] of Object.entries(form)) {
    if (CORE_BASE_TAG_KEYS.has(key)) core[key] = val
    else ai_outputs[key] = val
  }
  return { ...core, ai_outputs, version }
}

/** 将模板新增的动态输出字段并入列清单。 */
export function mergeAiColumns(baseCols: readonly DataColumn[], aiFields: string[]): DataColumn[] {
  const known = new Set(baseCols.map(col => col.prop))
  const extra = aiFields.filter(name => !known.has(name)).map(name => ({ prop: name, label: name, minWidth: 150, wrap: true }))
  return extra.length ? [...baseCols.slice(0, 7), ...extra, ...baseCols.slice(7)] : [...baseCols]
}

/** 「打标状态」筛选：AI 打标失败、要重打的，以及排着队的待办。和后端 policy.domain.fields.AI_STATUS_CHOICES 一致。 */
export const AI_STATUS_CHOICES = ['类型判断失败', '解读失败', '市场机会失败', '等待重新判断类型', '待解读', '待补市场机会']

/** 重新打标的三种：放回哪个任务的待办并自动启动后台执行、会发生什么。 */
export const RETAG_CHOICES = [
  {
    value: 'type',
    label: '重新判断类型',
    hint: '确定后将立即在后台启动「政策类型判断」重读并重新判断这些政策，覆盖现在的类型与判定字段，完成后页面会自动刷新并提示。会产生模型费用。',
  },
  {
    value: 'interpret',
    label: '重新解读',
    hint: '确定后将立即在后台启动「政策解读」重新生成解读结果，完成后页面会自动刷新并提示（已标为「人工验证」的解读行保留不覆盖）。只对「是否解读 = 是」的政策有效。会产生模型费用。',
  },
  {
    value: 'opportunity',
    label: '重新补市场机会',
    hint: '确定后将立即在后台启动「政策市场机会」重新生成并回填，完成后页面会自动刷新并提示。只对已解读的政策有效。会产生模型费用。',
  },
]
