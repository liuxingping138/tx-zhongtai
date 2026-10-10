import type { DataColumn } from '@/components/dataColumns'
import type { EditorGroup } from '@/components/editorGroups'

const FIELDS: { key: string; label: string }[] = [
  { key: 'prov_id', label: '省份编码' },
  { key: 'prov_name', label: '省份名称' },
  { key: 'city_id', label: '城市编码' },
  { key: 'city_name', label: '城市名称' },
  { key: 'county_id', label: '区县编码' },
  { key: 'county_name', label: '区县名称' },
  { key: 'alias_prov_name', label: '省份别名' },
  { key: 'alias_city_name', label: '城市别名' },
  { key: 'alias_county_name', label: '区县别名' },
  { key: 'city_name_short', label: '城市简称' },
  { key: 'county_name_short', label: '区县简称' },
]

export const TABLE_COLUMNS: DataColumn[] = [
  ...FIELDS.map((field) => ({
    prop: field.key,
    label: field.label,
    ...(field.key.endsWith('_id') ? { width: 112 } : { width: 160 }),
  })),
  { prop: 'created_at', label: '入库时间', width: 190, time: true },
  { prop: 'created_by_name', label: '入库人', width: 110 },
  { prop: 'updated_at', label: '更新时间', width: 190, time: true },
  { prop: 'updated_by_name', label: '操作人', width: 110 },
]

/** 窄屏卡片的摘要字段，也是列设置早期「精简默认列」的识别依据。 */
export const SUMMARY_KEYS = ['county_name', 'prov_name', 'city_name', 'county_id']

export const EDITOR_GROUPS: EditorGroup[] = [
  {
    title: '行政区划',
    hint: '区县编码为必填项，请保留原始编码格式。',
    fields: [
      { key: 'prov_id', label: '省份编码', maxLength: 64 },
      { key: 'prov_name', label: '省份名称', maxLength: 200 },
      { key: 'city_id', label: '城市编码', maxLength: 64 },
      { key: 'city_name', label: '城市名称', maxLength: 200 },
      { key: 'county_id', label: '区县编码', required: true, maxLength: 64 },
      { key: 'county_name', label: '区县名称', maxLength: 200 },
    ],
  },
  {
    title: '别名与简称',
    hint: '用于识别不同名称写法，无对应内容可留空。',
    fields: [
      { key: 'alias_prov_name', label: '省份别名', maxLength: 200 },
      { key: 'alias_city_name', label: '城市别名', maxLength: 200 },
      { key: 'alias_county_name', label: '区县别名', maxLength: 200 },
      { key: 'city_name_short', label: '城市简称', maxLength: 200 },
      { key: 'county_name_short', label: '区县简称', maxLength: 200 },
    ],
  },
]
