import type { DataColumn } from '@/components/dataColumns'
import type { EditorGroup } from '@/components/editorGroups'

export const TABLE_COLUMNS: DataColumn[] = [
  { prop: 'policy_name', label: '政策名称', minWidth: 320, grow: 2 },
  { prop: 'issuing_dept', label: '出台部门', width: 220 },
  { prop: 'issuer_industry', label: '发文机构行业', minWidth: 140 },
  { prop: 'policy_level', label: '政策层级', width: 110 },
  { prop: 'province_code', label: '省份编码', width: 100 },
  { prop: 'province_name', label: '省份名称', width: 110 },
  { prop: 'city_code', label: '地市编码', width: 100 },
  { prop: 'city_name', label: '地市名称', width: 110 },
  { prop: 'issued_at', label: '出台日期', fullLabel: '当前政策出台时间', width: 140 },
  { prop: 'policy_types', label: '政策类型', minWidth: 200, grow: 1, wrap: true },
  { prop: 'source_url', label: '原始网站链接', minWidth: 240, link: true },
  { prop: 'is_penetrate', label: '是否穿透', width: 100 },
  { prop: 'penetrate_words', label: '穿透词', minWidth: 180 },
  { prop: 'penetrate_score', label: '穿透词评分', width: 110 },
  { prop: 'need_interpret', label: '是否解读', width: 100 },
  { prop: 'remark', label: '备注', minWidth: 160 },
  { prop: 'created_at', label: '入库时间', width: 190, time: true },
  { prop: 'created_by_name', label: '入库人', width: 110 },
  { prop: 'updated_at', label: '更新时间', width: 190, time: true },
  { prop: 'updated_by_name', label: '操作人', width: 110 },
]

/** 窄屏卡片的摘要字段，也是列设置早期「精简默认列」的识别依据。 */
export const SUMMARY_KEYS = ['policy_name', 'province_name', 'policy_types', 'issued_at', 'need_interpret']

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
    hint: '填写政策分类、穿透和解读信息，便于后续筛选。',
    fields: [
      { key: 'policy_types', label: '政策类型' },
      { key: 'is_penetrate', label: '是否穿透', maxLength: 32 },
      { key: 'need_interpret', label: '是否解读', maxLength: 64 },
      { key: 'penetrate_score', label: '穿透词评分', maxLength: 64 },
      { key: 'penetrate_words', label: '穿透词', long: true },
      { key: 'remark', label: '备注', long: true },
    ],
  },
]
