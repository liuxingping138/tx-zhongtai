import type { DataColumn } from '@/components/dataColumns'
import type { EditorGroup } from '@/components/editorGroups'

const FIELDS: { key: string; label: string }[] = [
  { key: 'industry_scenario_code', label: '行业场景编码' },
  { key: 'industry_code', label: '行业编码' },
  { key: 'industry_l1', label: '项目一级行业' },
  { key: 'industry_l2', label: '项目二级行业' },
  { key: 'industry_l3', label: '项目三级行业' },
  { key: 'scenario_tag', label: '场景标签' },
  { key: 'scenario_level', label: '场景level' },
  { key: 'scenario_type', label: '场景类型' },
  { key: 'desc_90', label: '场景描述(90字)' },
  { key: 'desc_130', label: '场景描述(130字)' },
  { key: 'desc_pest', label: '场景描述(PEST总结)' },
  { key: 'scenario_source', label: '场景来源' },
  { key: 'scenario_hierarchy', label: '场景层级' },
  { key: 'scenario_code', label: '场景编码' },
  { key: 'scenario_l1_name', label: '项目一级场景名称' },
  { key: 'scenario_l1_desc', label: '项目一级场景描述' },
  { key: 'scenario_l2_name', label: '项目二级场景名称' },
  { key: 'scenario_l2_desc', label: '项目二级场景描述' },
  { key: 'scenario_l3_name', label: '项目三级场景名称' },
  { key: 'scenario_l3_desc', label: '项目三级场景描述' },
  { key: 'customer_group_name', label: '客群名称' },
  { key: 'customer_group_industry', label: '客群行业' },
  { key: 'org_keywords', label: '机构及企业名称包含关键词' },
  { key: 'scope_keywords', label: '经营范围包含' },
  { key: 'customer_level', label: '客户等级' },
  { key: 'customer_category', label: '客户类别' },
  { key: 'product_l1_name', label: '项目一级产品名称' },
  { key: 'product_l2_name', label: '项目二级产品名称' },
  { key: 'branch_count', label: '下属分支机构数' },
  { key: 'product_l1_sort', label: '一级产品排序（正序）' },
  { key: 'product_l2_sort', label: '二级产品排序（正序）' },
]

const LONG_FIELDS = new Set([
  'desc_90',
  'desc_130',
  'desc_pest',
  'scenario_l1_desc',
  'scenario_l2_desc',
  'scenario_l3_desc',
  'org_keywords',
  'scope_keywords',
])

const COLUMN_LABELS: Record<string, string> = {
  industry_l1: '一级行业',
  industry_l2: '二级行业',
  industry_l3: '三级行业',
  scenario_l1_name: '一级场景',
  scenario_l2_name: '二级场景',
  scenario_l3_name: '三级场景',
  scenario_l1_desc: '一级场景描述',
  scenario_l2_desc: '二级场景描述',
  scenario_l3_desc: '三级场景描述',
  org_keywords: '机构名称关键词',
  product_l1_name: '一级产品',
  product_l2_name: '二级产品',
  branch_count: '分支机构数',
  product_l1_sort: '一级产品排序',
  product_l2_sort: '二级产品排序',
}

export const TABLE_COLUMNS: DataColumn[] = [
  ...FIELDS.map((field) => ({
    prop: field.key,
    label: COLUMN_LABELS[field.key] || field.label,
    fullLabel: field.label,
    ...(LONG_FIELDS.has(field.key) ? { width: 300, wrap: true }
      : field.key === 'industry_scenario_code' ? { width: 220 }
      : field.key === 'scenario_tag' ? { minWidth: 220, grow: 1 }
      : field.key === 'customer_group_name' ? { minWidth: 230, grow: 2 }
      : field.key === 'product_l1_name' ? { minWidth: 180, grow: 1 }
      : { width: 160 }),
  })),
  { prop: 'created_at', label: '入库时间', width: 190, time: true },
  { prop: 'created_by_name', label: '入库人', width: 110 },
  { prop: 'updated_at', label: '更新时间', width: 190, time: true },
  { prop: 'updated_by_name', label: '操作人', width: 110 },
]

/** 窄屏卡片的摘要字段，也是列设置早期「精简默认列」的识别依据。 */
export const SUMMARY_KEYS = ['scenario_tag', 'industry_l1', 'customer_group_name', 'product_l1_name']

export const EDITOR_GROUPS: EditorGroup[] = [
  {
    title: '行业与场景标识',
    hint: '编码用于关联业务数据，请与现有码表保持一致。',
    fields: [
      { key: 'industry_scenario_code', label: '行业场景编码', maxLength: 64 },
      { key: 'industry_code', label: '行业编码', maxLength: 32 },
      { key: 'industry_l1', label: '项目一级行业', maxLength: 128 },
      { key: 'industry_l2', label: '项目二级行业', maxLength: 128 },
      { key: 'industry_l3', label: '项目三级行业', maxLength: 128 },
      { key: 'scenario_tag', label: '场景标签', maxLength: 255 },
      { key: 'scenario_level', label: '场景level', maxLength: 16 },
      { key: 'scenario_type', label: '场景类型', maxLength: 16 },
      { key: 'scenario_source', label: '场景来源' },
      { key: 'scenario_hierarchy', label: '场景层级', maxLength: 64 },
      { key: 'scenario_code', label: '场景编码', maxLength: 64 },
    ],
  },
  {
    title: '场景描述',
    hint: '分别填写不同用途的场景摘要和层级说明。',
    fields: [
      { key: 'desc_90', label: '场景描述(90字)', long: true },
      { key: 'desc_130', label: '场景描述(130字)', long: true },
      { key: 'desc_pest', label: '场景描述(PEST总结)', long: true },
      { key: 'scenario_l1_name', label: '项目一级场景名称', maxLength: 255 },
      { key: 'scenario_l1_desc', label: '项目一级场景描述', long: true },
      { key: 'scenario_l2_name', label: '项目二级场景名称', maxLength: 255 },
      { key: 'scenario_l2_desc', label: '项目二级场景描述', long: true },
      { key: 'scenario_l3_name', label: '项目三级场景名称', maxLength: 255 },
      { key: 'scenario_l3_desc', label: '项目三级场景描述', long: true },
    ],
  },
  {
    title: '目标客群',
    hint: '描述适用客群及筛选线索。',
    fields: [
      { key: 'customer_group_name', label: '客群名称', maxLength: 255 },
      { key: 'customer_group_industry', label: '客群行业', maxLength: 255 },
      { key: 'org_keywords', label: '机构及企业名称包含关键词', long: true },
      { key: 'scope_keywords', label: '经营范围包含', long: true },
      { key: 'customer_level', label: '客户等级', maxLength: 255 },
      { key: 'customer_category', label: '客户类别', maxLength: 255 },
    ],
  },
  {
    title: '产品与排序',
    hint: '补充产品名称及展示顺序，排序按正序填写。',
    fields: [
      { key: 'product_l1_name', label: '项目一级产品名称', maxLength: 255 },
      { key: 'product_l2_name', label: '项目二级产品名称', maxLength: 255 },
      { key: 'branch_count', label: '下属分支机构数', maxLength: 64 },
      { key: 'product_l1_sort', label: '一级产品排序（正序）', maxLength: 32 },
      { key: 'product_l2_sort', label: '二级产品排序（正序）', maxLength: 32 },
    ],
  },
]
