import type { DataColumn } from '@/components/dataColumns'
import type { EditorGroup } from '@/components/editorGroups'
import {
  DEPARTMENT_FALLBACK,
  displayCategory,
  FILE_TYPE_FALLBACK,
  INDUSTRY_FALLBACK,
  joinPipeTags,
  joinWhoWhen,
  MARKET_CATEGORY_FALLBACK,
  parseContentDispositionFilename,
  preferOptions,
  PRODUCT_TYPE_FALLBACK,
  PROVINCE_FALLBACK,
  splitPipeTags,
  suffixTagType,
  TAG_STATUS_OPTIONS,
} from '../shared/options'

export {
  joinPipeTags,
  parseContentDispositionFilename,
  splitPipeTags,
  suffixTagType,
  TAG_STATUS_OPTIONS,
}

export const FILE_TYPE_OPTIONS = [...FILE_TYPE_FALLBACK, '未定义'] as const
export const EDITABLE_FILE_TYPE_OPTIONS = [...FILE_TYPE_FALLBACK] as const
export const INDUSTRY_OPTIONS = [...INDUSTRY_FALLBACK] as const
export const DEPARTMENT_OPTIONS = [...DEPARTMENT_FALLBACK] as const
export const PROVINCE_OPTIONS = [...PROVINCE_FALLBACK] as const
export const OPERATOR_OPTIONS = ['未知', '电信', '联通', '移动'] as const
export const MARKET_CATEGORY_OPTIONS = [...MARKET_CATEGORY_FALLBACK] as const
export const PRODUCT_TYPE_OPTIONS = [...PRODUCT_TYPE_FALLBACK] as const
export const FAVORITE_OPTIONS = ['仅已收藏'] as const

export const FILTER_KEYS = [
  'file_name',
  'file_type',
  'operator_type',
  'product_type',
  'product_sub_type',
  'industry_type',
  'prov_name',
  'app_scenario',
  'depart_affiliation',
  'market_category',
  'data_time',
  'tag_status',
  'favorite_only',
] as const

/** 与后端和资料库清单页完全一致的 14 列。 */
export const TABLE_COLUMNS: DataColumn[] = [
  { prop: 'file_name', label: '资料名称', minWidth: 280, grow: 2, wrap: true },
  { prop: 'file_type', label: '文件类型', width: 135 },
  {
    prop: 'operator_type',
    label: '运营商类型',
    width: 100,
    tags: { 电信: 'primary', 移动: 'success', 联通: 'warning', 未知: 'info' },
  },
  { prop: 'depart_affiliation', label: '部门归属', width: 150 },
  { prop: 'industry_type', label: '行业类型', minWidth: 160, grow: 1, wrap: true },
  { prop: 'app_scenario', label: '应用场景', minWidth: 150, grow: 1, wrap: true },
  {
    prop: 'market_category',
    label: '市场类别',
    width: 96,
    tags: { 行客: 'primary', 商客: 'success', 综合: 'warning', 无: 'info' },
  },
  { prop: 'product_type', label: '产品类型', minWidth: 130, grow: 1, wrap: true },
  { prop: 'product_sub_type', label: '产品子类型', minWidth: 170, grow: 1, wrap: true },
  { prop: 'prov_name', label: '省份', width: 110 },
  { prop: 'data_time', label: '资料时间', width: 100 },
  { prop: 'uploaded_at', label: '上传时间', time: true, width: 190 },
  {
    prop: 'file_suffix',
    label: '文件后缀',
    width: 90,
    tags: { PDF: 'danger', PPT: 'warning', EXCEL: 'success', WORD: 'primary' },
  },
  { prop: 'file_size_display', label: '文件大小', width: 105 },
]

export const SUMMARY_KEYS = [
  'file_type',
  'operator_type',
  'industry_type',
  'market_category',
  'product_type',
  'prov_name',
  'data_time',
  'file_suffix',
  'file_size_display',
]

export const EDITOR_GROUPS: EditorGroup[] = [
  {
    title: '基本信息',
    hint: '修改文件类型或行业归属需具备对应范围的「可管理」权限。',
    fields: [
      { key: 'file_name', label: '资料名称', required: true, maxLength: 500, long: true },
      { key: 'file_type', label: '文件类型', choices: [...EDITABLE_FILE_TYPE_OPTIONS] },
      { key: 'operator_type', label: '运营商类型', choices: [...OPERATOR_OPTIONS] },
      { key: 'depart_affiliation', label: '部门归属', maxLength: 255 },
      { key: 'prov_name', label: '省份', maxLength: 64 },
      { key: 'data_time', label: '资料时间', maxLength: 32 },
    ],
  },
  {
    title: '行业与产品标签',
    hint: '多项行业或产品可用竖线 | 分隔，例如「中小|教育」。',
    fields: [
      { key: 'industry_type', label: '行业类型', maxLength: 255, long: true },
      { key: 'app_scenario', label: '应用场景', maxLength: 500, long: true },
      { key: 'market_category', label: '市场类别', choices: [...MARKET_CATEGORY_OPTIONS] },
      { key: 'product_type', label: '产品类型', maxLength: 255, long: true },
      { key: 'product_sub_type', label: '产品子类型', maxLength: 500, long: true },
      { key: 'remark', label: '备注', long: true },
    ],
  },
]

export const DETAIL_SYSTEM_COLUMNS: DataColumn[] = [
  { prop: 'file_suffix', label: '文件后缀' },
  { prop: 'file_size_display', label: '文件大小' },
  { prop: 'created_by_name', label: '上传人' },
  { prop: 'uploaded_at', label: '上传时间', time: true },
  { prop: 'updated_by_name', label: '最近更新人' },
  { prop: 'updated_at', label: '最近更新时间', time: true },
]

export interface KnowledgeDynamicOptions {
  file_type?: readonly string[]
  depart_affiliation?: readonly string[]
  industry_type?: readonly string[]
  product_type?: readonly string[]
  prov_name?: readonly string[]
  market_category?: readonly string[]
}

export type TextFieldKey =
  | 'file_name'
  | 'file_type'
  | 'operator_type'
  | 'depart_affiliation'
  | 'app_scenario'
  | 'market_category'
  | 'product_sub_type'
  | 'prov_name'
  | 'data_time'
  | 'remark'

export interface MetaFormSpec {
  key: TextFieldKey | 'industry_types' | 'product_types'
  label: string
  required?: boolean
  span?: boolean
  kind: 'input' | 'textarea' | 'select' | 'multi'
  options?: readonly string[]
  clearable?: boolean
  allowCreate?: boolean
}

export function buildMetaSectionSpecs(
  title: string,
  fileTypeChoices: readonly string[],
  canClearFileType: boolean,
  industryChoices: readonly string[],
  provinces: readonly string[],
  extra?: Pick<KnowledgeDynamicOptions, 'depart_affiliation' | 'product_type' | 'market_category'>,
): MetaFormSpec[] {
  const provinceChoices = preferOptions(provinces, PROVINCE_OPTIONS)
  const deptChoices = preferOptions(extra?.depart_affiliation, DEPARTMENT_OPTIONS)
  const marketChoices = preferOptions(extra?.market_category, MARKET_CATEGORY_OPTIONS)
  const productChoices = preferOptions(extra?.product_type, PRODUCT_TYPE_OPTIONS)
  if (title === '基本信息') {
    return [
      { key: 'file_name', label: '资料名称', required: true, span: true, kind: 'input' },
      { key: 'file_type', label: '文件类型', kind: 'select', options: fileTypeChoices, clearable: canClearFileType },
      { key: 'operator_type', label: '运营商类型', kind: 'select', options: OPERATOR_OPTIONS, clearable: true },
      { key: 'depart_affiliation', label: '部门归属', kind: 'select', options: deptChoices, clearable: true, allowCreate: true },
      { key: 'prov_name', label: '省份', kind: 'select', options: provinceChoices, clearable: true },
      { key: 'data_time', label: '资料时间', kind: 'input' },
    ]
  }
  if (title === '行业与产品标签') {
    return [
      { key: 'industry_types', label: '行业类型（可多选）', span: true, kind: 'multi', options: industryChoices },
      { key: 'app_scenario', label: '应用场景', span: true, kind: 'input' },
      { key: 'market_category', label: '市场类别', kind: 'select', options: marketChoices, clearable: true },
      { key: 'product_types', label: '产品类型（可多选）', span: true, kind: 'multi', options: productChoices },
      { key: 'product_sub_type', label: '产品子类型', span: true, kind: 'input' },
      { key: 'remark', label: '备注', span: true, kind: 'textarea' },
    ]
  }
  return []
}

export function displayFileType(value: string | undefined | null): string {
  return displayCategory(value)
}

export function buildKnowledgeFacts(r: {
  prov_name?: string
  file_type?: string
  operator_type?: string
  depart_affiliation?: string
  data_time?: string
  file_size_display?: string
  created_by_name?: string
  uploaded_at?: string
  updated_by_name?: string
  updated_at?: string
}, formatTimeFn: (val: string) => string): Array<{ label: string; value: string }> {
  return [
    { label: '省份', value: r.prov_name || '—' },
    { label: '文件类型', value: displayFileType(r.file_type) },
    { label: '运营商类型', value: r.operator_type || '—' },
    { label: '部门归属', value: r.depart_affiliation || '—' },
    { label: '资料时间', value: r.data_time || '—' },
    { label: '文件大小', value: r.file_size_display || '—' },
    { label: '上传', value: joinWhoWhen(r.created_by_name, r.uploaded_at, formatTimeFn) },
    { label: '最近更新', value: joinWhoWhen(r.updated_by_name, r.updated_at, formatTimeFn) },
  ]
}
