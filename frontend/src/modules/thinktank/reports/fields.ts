import type { ReportItem } from '@/api/thinktank'
import type { DataColumn } from '@/components/dataColumns'
import type { EditorGroup } from '@/components/editorGroups'
import type { SharedMetaFieldSpec, SummaryFact } from '../shared/metaFieldSpec'
import {
  DEPARTMENT_FALLBACK,
  displayCategory,
  INDUSTRY_FALLBACK,
  joinWhoWhen,
  preferOptions,
  PROVINCE_FALLBACK,
  TAG_STATUS_OPTIONS,
  YES_NO_OPTIONS,
} from '../shared/options'
import type { ThinktankFilterDef } from '../shared/ThinktankFilterGrid.vue'

export const REPORT_TYPE_FALLBACK = [
  '行业研究报告', '竞争分析报告', '专项调研报告', '市场分析报告',
  '可行性研究报告', '项目总结报告', '其他',
] as const

export const REPORT_FILTER_KEYS = [
  'report_name',
  'project_name',
  'customer_name',
  'report_type',
  'industry_tags',
  'region_tag',
  'delivery_dept',
  'participants',
  'is_temp_support',
  'delivery_date',
  'keywords',
  'tag_status',
  'favorite_only',
] as const

export const REPORT_FILTER_DEFS: readonly ThinktankFilterDef[] = [
  { field: 'report_name', label: '报告名称', placeholder: '输入关键词', kind: 'keyword' },
  { field: 'report_type', label: '报告类型', placeholder: '全部', kind: 'select', size: 'medium' },
  { field: 'industry_tags', label: '行业赛道', placeholder: '全部', kind: 'select', size: 'short' },
  { field: 'tag_status', label: '定义状态', placeholder: '全部', kind: 'select', size: 'short', fallbackOptions: TAG_STATUS_OPTIONS },
  { field: 'project_name', label: '所属项目', placeholder: '输入关键词', kind: 'keyword' },
  { field: 'customer_name', label: '客户名称', placeholder: '全部', kind: 'select', size: 'medium' },
  { field: 'region_tag', label: '区域标签', placeholder: '全部', kind: 'select', size: 'short' },
  { field: 'delivery_dept', label: '交付部门', placeholder: '全部', kind: 'select', size: 'medium' },
  { field: 'is_temp_support', label: '临时支撑', placeholder: '全部', kind: 'select', size: 'short', fallbackOptions: YES_NO_OPTIONS },
  { field: 'delivery_date', label: '交付日期', placeholder: '全部', kind: 'select', size: 'short' },
  { field: 'participants', label: '参与人员', placeholder: '输入关键词', kind: 'keyword' },
  { field: 'keywords', label: '关键词', placeholder: '输入关键词', kind: 'keyword' },
  { field: 'favorite_only', label: '我的收藏', placeholder: '全部', kind: 'select', size: 'short', fallbackOptions: ['仅看收藏'] },
]

export const REPORT_TABLE_COLUMNS: DataColumn[] = [
  { prop: 'report_name', label: '报告名称', minWidth: 260, grow: 2, wrap: true },
  { prop: 'project_name', label: '所属项目', minWidth: 150, grow: 1, wrap: true },
  { prop: 'customer_name', label: '客户名称', minWidth: 150, grow: 1, wrap: true },
  { prop: 'report_type', label: '报告类型', width: 130 },
  { prop: 'industry_tags', label: '行业赛道标签', minWidth: 150, grow: 1, wrap: true },
  { prop: 'region_tag', label: '区域标签', width: 110 },
  { prop: 'delivery_dept', label: '交付部门', width: 140 },
  { prop: 'participants', label: '参与人员', minWidth: 130, grow: 1, wrap: true },
  {
    prop: 'is_temp_support',
    label: '是否临时支撑',
    width: 112,
    tags: { 是: 'warning', 否: 'info' },
  },
  { prop: 'delivery_date', label: '交付日期', width: 115 },
  { prop: 'summary', label: '核心结论摘要(≤100字)', minWidth: 210, grow: 1, wrap: true },
  { prop: 'keywords', label: '关键词(3-5个)', minWidth: 150, grow: 1, wrap: true },
  { prop: 'data_sources', label: '主要数据来源', minWidth: 150, grow: 1, wrap: true },
  { prop: 'uploaded_at', label: '上传时间', time: true, width: 190 },
  {
    prop: 'file_suffix',
    label: '文件后缀',
    width: 90,
    tags: { PDF: 'danger', PPT: 'warning', EXCEL: 'success', WORD: 'primary' },
  },
  { prop: 'file_size_display', label: '文件大小', width: 105 },
]

export const REPORT_SUMMARY_KEYS = [
  'report_type',
  'customer_name',
  'industry_tags',
  'region_tag',
  'delivery_dept',
  'delivery_date',
  'file_suffix',
  'file_size_display',
]

export const REPORT_EDITOR_GROUPS: EditorGroup[] = [
  {
    title: '基本信息',
    hint: '完善报告基础分类，便于检索与沉淀。',
    fields: [
      { key: 'report_name', label: '报告名称', required: true, maxLength: 500, long: true },
      { key: 'project_name', label: '所属项目', maxLength: 255 },
      { key: 'customer_name', label: '客户名称', maxLength: 255 },
      { key: 'report_type', label: '报告类型', maxLength: 128 },
      { key: 'industry_tags', label: '行业赛道标签', maxLength: 255, long: true },
      { key: 'region_tag', label: '区域标签', maxLength: 128 },
    ],
  },
  {
    title: '交付信息',
    hint: '记录交付团队、时间及临时支撑属性。',
    fields: [
      { key: 'delivery_dept', label: '交付部门', maxLength: 255 },
      { key: 'participants', label: '参与人员', maxLength: 500 },
      { key: 'is_temp_support', label: '是否临时支撑', choices: [...YES_NO_OPTIONS] },
      { key: 'delivery_date', label: '交付日期', date: true },
    ],
  },
  {
    title: '内容摘要与来源',
    hint: '提炼不超过 100 字的核心结论与 3-5 个关键词。',
    fields: [
      { key: 'summary', label: '核心结论摘要(≤100字)', maxLength: 100, long: true },
      { key: 'keywords', label: '关键词(3-5个)', maxLength: 500, long: true },
      { key: 'data_sources', label: '主要数据来源', long: true },
      { key: 'remark', label: '备注', long: true },
    ],
  },
]

export const REPORT_SYSTEM_COLUMNS: DataColumn[] = [
  { prop: 'file_suffix', label: '文件后缀' },
  { prop: 'file_size_display', label: '文件大小' },
  { prop: 'created_by_name', label: '上传人' },
  { prop: 'uploaded_at', label: '上传时间', time: true },
  { prop: 'updated_by_name', label: '最近更新人' },
  { prop: 'updated_at', label: '最近更新时间', time: true },
]

export interface ReportDynamicOptions {
  report_type?: readonly string[]
  industry_tags?: readonly string[]
  region_tag?: readonly string[]
  delivery_dept?: readonly string[]
  is_temp_support?: readonly string[]
}

export function buildReportMetaSpecs(options: ReportDynamicOptions = {}): Record<string, SharedMetaFieldSpec[]> {
  const reportTypes = preferOptions(options.report_type, REPORT_TYPE_FALLBACK)
  const industries = preferOptions(options.industry_tags, INDUSTRY_FALLBACK)
  const regions = preferOptions(options.region_tag, PROVINCE_FALLBACK)
  const depts = preferOptions(options.delivery_dept, DEPARTMENT_FALLBACK)
  const tempChoices = preferOptions(options.is_temp_support, YES_NO_OPTIONS)
  return {
    基本信息: [
      { key: 'report_name', label: '报告名称', required: true, span: true, kind: 'input', maxlength: 500 },
      { key: 'project_name', label: '所属项目', kind: 'input', maxlength: 255 },
      { key: 'customer_name', label: '客户名称', kind: 'input', maxlength: 255 },
      { key: 'report_type', label: '报告类型', kind: 'select', options: reportTypes, allowCreate: true },
      { key: 'region_tag', label: '区域标签', kind: 'select', options: regions },
      { key: 'industry_tags', label: '行业赛道标签（可多选）', span: true, kind: 'multi', options: industries },
    ],
    交付信息: [
      { key: 'delivery_dept', label: '交付部门', kind: 'select', options: depts, allowCreate: true },
      { key: 'participants', label: '参与人员', kind: 'input', maxlength: 500 },
      { key: 'is_temp_support', label: '是否临时支撑', kind: 'select', options: tempChoices },
      { key: 'delivery_date', label: '交付日期', kind: 'date' },
    ],
    内容摘要与来源: [
      { key: 'summary', label: '核心结论摘要(≤100字)', span: true, kind: 'textarea', maxlength: 100, rows: 3 },
      { key: 'keywords', label: '关键词(3-5个)', span: true, kind: 'input', maxlength: 500 },
      { key: 'data_sources', label: '主要数据来源', span: true, kind: 'textarea', rows: 2 },
      { key: 'remark', label: '备注', span: true, kind: 'textarea', rows: 2 },
    ],
  }
}

export function validateReportForm(values: Record<string, string | string[]>): Record<string, string> {
  const errors: Record<string, string> = {}
  const name = typeof values.report_name === 'string' ? values.report_name.trim() : ''
  if (!name) errors.report_name = '请填写报告名称'
  const summary = typeof values.summary === 'string' ? values.summary.trim() : ''
  if (summary.length > 100) errors.summary = '核心结论摘要不能超过 100 字'
  return errors
}

export function buildReportFacts(
  item: Partial<ReportItem>,
  formatTimeFn: (val: string) => string,
): SummaryFact[] {
  return [
    { label: '报告类型', value: displayCategory(item.report_type) },
    { label: '客户名称', value: item.customer_name || '—' },
    { label: '区域标签', value: item.region_tag || '—' },
    { label: '交付部门', value: item.delivery_dept || '—' },
    { label: '交付日期', value: item.delivery_date || '—' },
    { label: '文件大小', value: item.file_size_display || '—' },
    { label: '上传', value: joinWhoWhen(item.created_by_name, item.uploaded_at, formatTimeFn) },
    { label: '最近更新', value: joinWhoWhen(item.updated_by_name, item.updated_at, formatTimeFn) },
  ]
}
