import type { DataColumn } from '@/components/dataColumns'
import type { EditorGroup } from '@/components/editorGroups'

/** 与后端 DATA_STATUS_CHOICES 一致，只允许这两项。 */
export const DATA_STATUS_CHOICES = ['待验证', '人工验证']

// 列的先后按核对的顺序：先是这一行解读出的行业、场景，紧跟着核对时最先看的机会类型、信息化等级和两个状态，
// 再是 AI 写的客户、产品、要文、补贴、市场机会；编码、唯一标识、关联主键这类对人没意义的放后面，留痕列最后。
// ai 标的是 AI 打标写入的列
// （aitag/domain/interpret_rules.ANSWER_FIELDS 和市场机会那一步）；是否新增场景、新增场景级别由码表比对结果覆盖，不算。
// 详情按下面的 EDITOR_GROUPS 分组展示。
export const TABLE_COLUMNS: DataColumn[] = [
  { prop: 'policy_title', label: '政策原文名称', minWidth: 340, grow: 2 },
  // 行业、场景各叠成一格：上面一级，下面浅色的二级 › 三级（2026-11-03：原来六列都被挤成截断的半句）
  { prop: 'industry_l1', label: '行业', fullLabel: '一级行业，下面是二级 › 三级行业', minWidth: 220, stack: ['industry_l2', 'industry_l3'], ai: true },
  { prop: 'scenario_l1_name', label: '场景', fullLabel: '一级场景，下面是二级 › 三级场景', minWidth: 220, grow: 1, stack: ['scenario_l2_name', 'scenario_l3_name'], ai: true },
  { prop: 'opportunity_type', label: '机会类型', width: 116, ai: true },
  { prop: 'info_level', label: '信息化等级', width: 124, ai: true },
  { prop: 'scenario_state', label: '场景状态', width: 120 },
  { prop: 'data_status', label: '数据状态', width: 110 },
  { prop: 'target_customers', label: '目标客户', fullLabel: '目标客户当前政策影响客户群', minWidth: 260, grow: 1, wrap: true, ai: true },
  { prop: 'adapted_products', label: '适配产品', minWidth: 180, ai: true },
  { prop: 'purchase_reason', label: '采买理由', fullLabel: '目标客户采买理由', minWidth: 200, ai: true },
  { prop: 'policy_summary', label: '政策要文', width: 320, wrap: true, ai: true },
  { prop: 'has_subsidy', label: '有无政府补贴', width: 136, ai: true },
  { prop: 'subsidy_content', label: '补贴内容', minWidth: 180, ai: true },
  { prop: 'market_opportunity', label: '政策市场机会', minWidth: 180, ai: true },
  { prop: 'is_new_scenario', label: '是否新增场景', width: 120 },
  { prop: 'new_scenario_level', label: '新增场景级别', width: 120 },
  { prop: 'remark', label: '备注', minWidth: 200 },
  { prop: 'industry_scenario_code', label: '行业场景编码', width: 220 },
  { prop: 'industry_code', label: '行业编码', width: 120 },
  { prop: 'scenario_code', label: '场景编码', width: 140 },
  { prop: 'policy_uid', label: '政策唯一标识', width: 300 },
  { prop: 'relation_key', label: '关联主键', minWidth: 200 },
  { prop: 'scenario_synced_at', label: '场景同步时间', width: 190, time: true },
  { prop: 'created_at', label: '入库时间', width: 190, time: true },
  { prop: 'created_by_name', label: '入库人', width: 110 },
  { prop: 'updated_at', label: '更新时间', width: 190, time: true },
  { prop: 'updated_by_name', label: '操作人', width: 110 },
]

/** 窄屏卡片的摘要字段，也是列设置早期「精简默认列」的识别依据。 */
export const SUMMARY_KEYS = ['policy_title', 'opportunity_type', 'target_customers', 'has_subsidy']

/** 列表的筛选字段，和列表页 query 里的一致；核对页靠它从地址栏带上筛选，翻上一条、下一条。 */
export const FILTER_KEYS = ['policy_title', 'industry_l1', 'scenario_l1_name', 'opportunity_type', 'is_new_scenario', 'new_scenario_level', 'info_level', 'data_status', 'scenario_state']

// 分组按核对的顺序：基本信息，行业与场景（同级的行业和场景并排，方便对照层级），AI 写的解读内容，最后是机会与补贴。
// 新增、编辑和详情用同一套分组；表单里没有的政策唯一标识、关联主键和入库更新记录，详情里归到「系统信息」。
export const EDITOR_GROUPS: EditorGroup[] = [
  {
    title: '基本信息',
    hint: '政策原文名称必填；新录入默认待验证。',
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
    ],
  },
  {
    title: '行业与场景',
    hint: '行业和场景按级别对照填写，编码请与场景码表保持一致；新增场景时填写相应级别。',
    fields: [
      { key: 'industry_l1', label: '一级行业', maxLength: 128 },
      { key: 'scenario_l1_name', label: '一级场景名称', maxLength: 255 },
      { key: 'industry_l2', label: '二级行业', maxLength: 128 },
      { key: 'scenario_l2_name', label: '二级场景名称', maxLength: 255 },
      { key: 'industry_l3', label: '三级行业', maxLength: 128 },
      { key: 'scenario_l3_name', label: '三级场景名称', maxLength: 255 },
      { key: 'industry_code', label: '行业编码', maxLength: 32 },
      { key: 'scenario_code', label: '场景编码', maxLength: 64 },
      { key: 'industry_scenario_code', label: '行业场景编码', maxLength: 128 },
      { key: 'is_new_scenario', label: '是否新增场景', maxLength: 32 },
      { key: 'new_scenario_level', label: '新增场景级别', maxLength: 64 },
    ],
  },
  {
    title: '解读内容',
    hint: '先概括政策内容，再写目标客户、适配产品、采买理由和市场机会。',
    fields: [
      { key: 'policy_summary', label: '政策要文', long: true },
      { key: 'target_customers', label: '目标客户当前政策影响客户群', long: true },
      { key: 'adapted_products', label: '适配产品', long: true },
      { key: 'purchase_reason', label: '目标客户采买理由', long: true },
      { key: 'market_opportunity', label: '政策市场机会', long: true },
    ],
  },
  {
    title: '机会与补贴',
    hint: '机会类型、补贴和信息化等级用于筛选和统计。',
    fields: [
      { key: 'opportunity_type', label: '机会类型', maxLength: 64 },
      { key: 'has_subsidy', label: '有无政府补贴', maxLength: 32 },
      { key: 'info_level', label: '信息化等级', maxLength: 32 },
      { key: 'subsidy_content', label: '补贴内容', long: true },
      { key: 'remark', label: '备注', long: true },
    ],
  },
]
