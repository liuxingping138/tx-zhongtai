import type { ProposalItem } from '@/api/thinktank'
import type { DataColumn } from '@/components/dataColumns'
import type { EditorGroup } from '@/components/editorGroups'
import type { ExtraStatusTag, SharedMetaFieldSpec, SummaryFact } from '../shared/metaFieldSpec'
import {
  DEPARTMENT_FALLBACK,
  displayCategory,
  INDUSTRY_FALLBACK,
  joinWhoWhen,
  preferOptions,
  PROPOSAL_RESULT_OPTIONS,
  PROVINCE_FALLBACK,
  TAG_STATUS_OPTIONS,
} from '../shared/options'
import type { ThinktankFilterDef } from '../shared/ThinktankFilterGrid.vue'

export const PROPOSAL_TYPE_FALLBACK = [
  '技术方案', '投标方案', '解决方案', '规划咨询方案', '运维服务方案', '其他',
] as const

export const OPPORTUNITY_SOURCE_FALLBACK = [
  '自主拓展', '客户邀标', '合作伙伴', '招投标平台', '生态合作', '其他',
] as const

export const BIDDING_METHOD_FALLBACK = [
  '公开招标', '邀请招标', '竞争性磋商', '竞争性谈判', '单一来源', '询价采购', '其他',
] as const

export const PROPOSAL_RESULT_TAGS: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
  中标: 'success',
  未中标: 'danger',
  待定: 'warning',
  流标: 'info',
}

export const PROPOSAL_FILTER_KEYS = [
  'proposal_name',
  'customer_name',
  'proposal_type',
  'industry_tags',
  'region_tag',
  'opportunity_source',
  'bidding_method',
  'bid_deadline',
  'owner_dept',
  'owner_name',
  'result_status',
  'tag_status',
  'favorite_only',
] as const

export const PROPOSAL_FILTER_DEFS: readonly ThinktankFilterDef[] = [
  { field: 'proposal_name', label: '方案名称', placeholder: '输入关键词', kind: 'keyword' },
  { field: 'proposal_type', label: '方案类型', placeholder: '全部', kind: 'select', size: 'medium' },
  { field: 'industry_tags', label: '行业赛道', placeholder: '全部', kind: 'select', size: 'short' },
  { field: 'result_status', label: '结果', placeholder: '全部', kind: 'select', size: 'short', fallbackOptions: PROPOSAL_RESULT_OPTIONS },
  { field: 'customer_name', label: '客户名称', placeholder: '全部', kind: 'select', size: 'medium' },
  { field: 'region_tag', label: '区域标签', placeholder: '全部', kind: 'select', size: 'short' },
  { field: 'opportunity_source', label: '商机来源', placeholder: '全部', kind: 'select', size: 'medium' },
  { field: 'bidding_method', label: '招标方式', placeholder: '全部', kind: 'select', size: 'medium' },
  { field: 'bid_deadline', label: '投标截止', placeholder: '全部', kind: 'select', size: 'short' },
  { field: 'owner_dept', label: '负责部门', placeholder: '全部', kind: 'select', size: 'medium' },
  { field: 'owner_name', label: '负责人', placeholder: '输入关键词', kind: 'keyword' },
  { field: 'tag_status', label: '定义状态', placeholder: '全部', kind: 'select', size: 'short', fallbackOptions: TAG_STATUS_OPTIONS },
  { field: 'favorite_only', label: '我的收藏', placeholder: '全部', kind: 'select', size: 'short', fallbackOptions: ['仅看收藏'] },
]

export const PROPOSAL_TABLE_COLUMNS: DataColumn[] = [
  { prop: 'proposal_name', label: '方案名称', minWidth: 260, grow: 2, wrap: true },
  { prop: 'customer_name', label: '客户名称', minWidth: 150, grow: 1, wrap: true },
  { prop: 'proposal_type', label: '方案类型', width: 130 },
  { prop: 'industry_tags', label: '行业赛道标签', minWidth: 150, grow: 1, wrap: true },
  { prop: 'region_tag', label: '区域标签', width: 110 },
  { prop: 'opportunity_source', label: '商机来源', width: 120 },
  { prop: 'bidding_method', label: '招标方式', width: 120 },
  { prop: 'bid_deadline', label: '投标截止日期', width: 125 },
  { prop: 'owner_dept', label: '方案负责部门', width: 140 },
  { prop: 'owner_name', label: '方案负责人', width: 110 },
  { prop: 'quote_amount', label: '报价(万元)', width: 110 },
  { prop: 'result_status', label: '结果', width: 96, tags: PROPOSAL_RESULT_TAGS },
  { prop: 'win_amount', label: '中标金额(万元)', width: 125 },
  { prop: 'selling_points', label: '方案核心卖点摘要(≤100字)', minWidth: 220, grow: 1, wrap: true },
  { prop: 'uploaded_at', label: '上传时间', time: true, width: 190 },
  {
    prop: 'file_suffix',
    label: '文件后缀',
    width: 90,
    tags: { PDF: 'danger', PPT: 'warning', EXCEL: 'success', WORD: 'primary' },
  },
  { prop: 'file_size_display', label: '文件大小', width: 105 },
]

export const PROPOSAL_SUMMARY_KEYS = [
  'proposal_type',
  'customer_name',
  'industry_tags',
  'region_tag',
  'owner_dept',
  'result_status',
  'quote_amount',
  'file_suffix',
  'file_size_display',
]

export const PROPOSAL_EDITOR_GROUPS: EditorGroup[] = [
  {
    title: '基本信息',
    hint: '完善方案基础分类、行业赛道与客户归属。',
    fields: [
      { key: 'proposal_name', label: '方案名称', required: true, maxLength: 500, long: true },
      { key: 'customer_name', label: '客户名称', maxLength: 255 },
      { key: 'proposal_type', label: '方案类型', maxLength: 128 },
      { key: 'industry_tags', label: '行业赛道标签', maxLength: 255, long: true },
      { key: 'region_tag', label: '区域标签', maxLength: 128 },
      { key: 'owner_dept', label: '方案负责部门', maxLength: 255 },
      { key: 'owner_name', label: '方案负责人', maxLength: 128 },
    ],
  },
  {
    title: '招投标与报价',
    hint: '记录商机来源、招标方式、报价及中标结果。',
    fields: [
      { key: 'opportunity_source', label: '商机来源', maxLength: 128 },
      { key: 'bidding_method', label: '招标方式', maxLength: 128 },
      { key: 'bid_deadline', label: '投标截止日期', date: true },
      { key: 'quote_amount', label: '报价(万元)', maxLength: 64 },
      { key: 'result_status', label: '结果', choices: [...PROPOSAL_RESULT_OPTIONS] },
      { key: 'win_amount', label: '中标金额(万元)', maxLength: 64 },
    ],
  },
  {
    title: '核心卖点与备注',
    hint: '提炼不超过 100 字的方案核心卖点摘要。',
    fields: [
      { key: 'selling_points', label: '方案核心卖点摘要(≤100字)', maxLength: 100, long: true },
      { key: 'remark', label: '备注', long: true },
    ],
  },
]

export const PROPOSAL_SYSTEM_COLUMNS: DataColumn[] = [
  { prop: 'file_suffix', label: '文件后缀' },
  { prop: 'file_size_display', label: '文件大小' },
  { prop: 'created_by_name', label: '上传人' },
  { prop: 'uploaded_at', label: '上传时间', time: true },
  { prop: 'updated_by_name', label: '最近更新人' },
  { prop: 'updated_at', label: '最近更新时间', time: true },
]

export interface ProposalDynamicOptions {
  proposal_type?: readonly string[]
  industry_tags?: readonly string[]
  region_tag?: readonly string[]
  opportunity_source?: readonly string[]
  bidding_method?: readonly string[]
  owner_dept?: readonly string[]
  result_status?: readonly string[]
}

export function buildProposalMetaSpecs(options: ProposalDynamicOptions = {}): Record<string, SharedMetaFieldSpec[]> {
  const proposalTypes = preferOptions(options.proposal_type, PROPOSAL_TYPE_FALLBACK)
  const industries = preferOptions(options.industry_tags, INDUSTRY_FALLBACK)
  const regions = preferOptions(options.region_tag, PROVINCE_FALLBACK)
  const sources = preferOptions(options.opportunity_source, OPPORTUNITY_SOURCE_FALLBACK)
  const methods = preferOptions(options.bidding_method, BIDDING_METHOD_FALLBACK)
  const depts = preferOptions(options.owner_dept, DEPARTMENT_FALLBACK)
  const results = preferOptions(options.result_status, PROPOSAL_RESULT_OPTIONS)
  return {
    基本信息: [
      { key: 'proposal_name', label: '方案名称', required: true, span: true, kind: 'input', maxlength: 500 },
      { key: 'customer_name', label: '客户名称', kind: 'input', maxlength: 255 },
      { key: 'proposal_type', label: '方案类型', kind: 'select', options: proposalTypes, allowCreate: true },
      { key: 'region_tag', label: '区域标签', kind: 'select', options: regions },
      { key: 'owner_dept', label: '方案负责部门', kind: 'select', options: depts, allowCreate: true },
      { key: 'owner_name', label: '方案负责人', kind: 'input', maxlength: 128 },
      { key: 'industry_tags', label: '行业赛道标签（可多选）', span: true, kind: 'multi', options: industries },
    ],
    招投标与报价: [
      { key: 'opportunity_source', label: '商机来源', kind: 'select', options: sources, allowCreate: true },
      { key: 'bidding_method', label: '招标方式', kind: 'select', options: methods, allowCreate: true },
      { key: 'bid_deadline', label: '投标截止日期', kind: 'date' },
      { key: 'quote_amount', label: '报价(万元)', kind: 'input', maxlength: 64, placeholder: '如 120.5' },
      { key: 'result_status', label: '结果', kind: 'select', options: results },
      { key: 'win_amount', label: '中标金额(万元)', kind: 'input', maxlength: 64, placeholder: '如 115.0' },
    ],
    核心卖点与备注: [
      { key: 'selling_points', label: '方案核心卖点摘要(≤100字)', span: true, kind: 'textarea', maxlength: 100, rows: 3 },
      { key: 'remark', label: '备注', span: true, kind: 'textarea', rows: 2 },
    ],
  }
}

export function validateProposalForm(values: Record<string, string | string[]>): Record<string, string> {
  const errors: Record<string, string> = {}
  const name = typeof values.proposal_name === 'string' ? values.proposal_name.trim() : ''
  if (!name) errors.proposal_name = '请填写方案名称'
  const points = typeof values.selling_points === 'string' ? values.selling_points.trim() : ''
  if (points.length > 100) errors.selling_points = '方案核心卖点摘要不能超过 100 字'
  return errors
}

export function proposalResultTag(status: string | undefined | null): ExtraStatusTag | null {
  const trimmed = status?.trim() ?? ''
  if (!trimmed) return null
  return { label: trimmed, type: PROPOSAL_RESULT_TAGS[trimmed] ?? 'info' }
}

export function buildProposalFacts(
  item: Partial<ProposalItem>,
  formatTimeFn: (val: string) => string,
): SummaryFact[] {
  return [
    { label: '方案类型', value: displayCategory(item.proposal_type) },
    { label: '客户名称', value: item.customer_name || '—' },
    { label: '区域标签', value: item.region_tag || '—' },
    { label: '负责部门', value: item.owner_dept || '—' },
    { label: '负责人', value: item.owner_name || '—' },
    { label: '报价(万元)', value: item.quote_amount || '—' },
    { label: '中标金额(万元)', value: item.win_amount || '—' },
    { label: '文件大小', value: item.file_size_display || '—' },
    { label: '上传', value: joinWhoWhen(item.created_by_name, item.uploaded_at, formatTimeFn) },
    { label: '最近更新', value: joinWhoWhen(item.updated_by_name, item.updated_at, formatTimeFn) },
  ]
}
