import type { DataColumn } from '@/components/dataColumns'
import type { EditorGroup } from '@/components/editorGroups'

/** 与后端 DATA_STATUS_CHOICES 一致，只允许这两项。 */
export const DATA_STATUS_CHOICES = ['待验证', '人工验证']

/** 新录入默认待验证。 */
export const EDITOR_DEFAULTS = { data_status: '待验证' }

export const TABLE_COLUMNS: DataColumn[] = [
  { prop: 'policy_uid', label: '政策唯一标识', width: 300 },
  { prop: 'policy_title', label: '政策原文名称', minWidth: 340, grow: 2 },
  { prop: 'industry_scenario_code', label: '行业场景编码', width: 220 },
  { prop: 'industry_code', label: '行业编码', width: 120 },
  { prop: 'industry_l1', label: '一级行业', width: 120 },
  { prop: 'industry_l2', label: '二级行业', width: 120 },
  { prop: 'industry_l3', label: '三级行业', width: 120 },
  { prop: 'scenario_code', label: '场景编码', width: 140 },
  { prop: 'scenario_l1_name', label: '一级场景名称', minWidth: 140 },
  { prop: 'scenario_l2_name', label: '二级场景名称', minWidth: 140 },
  { prop: 'scenario_l3_name', label: '三级场景名称', minWidth: 140 },
  { prop: 'target_customers', label: '目标客户', fullLabel: '目标客户当前政策影响客户群', minWidth: 260, grow: 1, wrap: true },
  { prop: 'relation_key', label: '关联主键', minWidth: 200 },
  { prop: 'opportunity_type', label: '机会类型', width: 110 },
  { prop: 'policy_summary', label: '政策要文', width: 320, wrap: true },
  { prop: 'has_subsidy', label: '有无政府补贴', width: 120 },
  { prop: 'subsidy_content', label: '补贴内容', minWidth: 180 },
  { prop: 'market_opportunity', label: '政策市场机会', minWidth: 180 },
  { prop: 'info_level', label: '信息化等级', width: 110 },
  { prop: 'is_new_scenario', label: '是否新增场景', width: 120 },
  { prop: 'new_scenario_level', label: '新增场景级别', width: 120 },
  { prop: 'data_status', label: '数据状态', width: 110 },
  { prop: 'created_at', label: '入库时间', width: 190, time: true },
  { prop: 'created_by_name', label: '入库人', width: 110 },
  { prop: 'updated_at', label: '更新时间', width: 190, time: true },
  { prop: 'updated_by_name', label: '操作人', width: 110 },
]

/** 窄屏卡片的摘要字段，也是列设置早期「精简默认列」的识别依据。 */
export const SUMMARY_KEYS = ['policy_title', 'opportunity_type', 'target_customers', 'has_subsidy']

export const EDITOR_GROUPS: EditorGroup[] = [
  {
    title: '政策与行业',
    hint: '填写政策名称并关联行业场景，编码请与场景码表保持一致。',
    fields: [
      { key: 'policy_title', label: '政策原文名称', long: true, required: true },
      {
        key: 'data_status',
        label: '数据状态',
        hint: '新录入默认待验证；人工核对无误后改为人工验证。',
        required: true,
        choices: DATA_STATUS_CHOICES,
      },
      { key: 'tenant_id', label: '租户标识', hint: '对应数据所属租户，无租户标识时可留空。', maxLength: 64 },
      { key: 'industry_scenario_code', label: '行业场景编码', maxLength: 128 },
      { key: 'industry_code', label: '行业编码', maxLength: 32 },
      { key: 'industry_l1', label: '一级行业', maxLength: 128 },
      { key: 'industry_l2', label: '二级行业', maxLength: 128 },
      { key: 'industry_l3', label: '三级行业', maxLength: 128 },
    ],
  },
  {
    title: '场景信息',
    hint: '补充场景层级；新增场景时填写相应级别。',
    fields: [
      { key: 'scenario_code', label: '场景编码', maxLength: 64 },
      { key: 'scenario_l1_name', label: '一级场景名称', maxLength: 255 },
      { key: 'scenario_l2_name', label: '二级场景名称', maxLength: 255 },
      { key: 'scenario_l3_name', label: '三级场景名称', maxLength: 255 },
      { key: 'is_new_scenario', label: '是否新增场景', maxLength: 32 },
      { key: 'new_scenario_level', label: '新增场景级别', maxLength: 64 },
    ],
  },
  {
    title: '解读与业务机会',
    hint: '先概括政策内容，再描述目标客户、补贴及市场机会。',
    fields: [
      { key: 'policy_summary', label: '政策要文', long: true },
      { key: 'target_customers', label: '目标客户当前政策影响客户群', long: true },
      { key: 'opportunity_type', label: '机会类型', maxLength: 64 },
      { key: 'has_subsidy', label: '有无政府补贴', maxLength: 32 },
      { key: 'subsidy_content', label: '补贴内容', long: true },
      { key: 'market_opportunity', label: '政策市场机会', long: true },
      { key: 'info_level', label: '信息化等级', maxLength: 32 },
    ],
  },
]
