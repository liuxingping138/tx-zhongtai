import type { DataColumn } from '@/components/dataColumns'
import type { EditorGroup } from '@/components/editorGroups'

export const TABLE_COLUMNS: DataColumn[] = [
  { prop: 'site_name', label: '网站名称', minWidth: 240, grow: 2 },
  { prop: 'province_name', label: '省份', width: 100 },
  { prop: 'city_name', label: '地市', width: 110 },
  { prop: 'district_name', label: '区县', width: 120 },
  { prop: 'crawl_priority', label: '抓取优先级', fullLabel: '网站梳理和抓取的优先级', width: 120 },
  { prop: 'url', label: '链接', minWidth: 240, link: true },
  { prop: 'tag', label: '标签', minWidth: 200, grow: 1 },
  {
    prop: 'data_type',
    label: '数据类型',
    fullLabel: '数据类型（综合-0、政策-1、新闻-2）注：0和1链接下全爬，2爬聚集板块',
    width: 120,
  },
  { prop: 'department', label: '所属部门', width: 220 },
  { prop: 'created_at', label: '入库时间', width: 190, time: true },
  { prop: 'created_by_name', label: '入库人', width: 110 },
  { prop: 'updated_at', label: '更新时间', width: 190, time: true },
  { prop: 'updated_by_name', label: '操作人', width: 110 },
]

/** 窄屏卡片的摘要字段，也是列设置早期「精简默认列」的识别依据。 */
export const SUMMARY_KEYS = ['site_name', 'province_name', 'city_name', 'tag', 'crawl_priority']

export const EDITOR_GROUPS: EditorGroup[] = [
  {
    title: '基础信息',
    hint: '填写信源网站与所属部门，便于识别和维护。',
    fields: [
      { key: 'site_name', label: '网站名称', required: true, maxLength: 255 },
      { key: 'department', label: '所属部门', maxLength: 255 },
      { key: 'url', label: '网站链接', long: true, placeholder: 'https://', hint: '建议填写完整的网址，便于直接访问。' },
    ],
  },
  {
    title: '所属地区',
    hint: '省、市、区县编码至少填写一项；名称与编码请保持对应。',
    fields: [
      { key: 'province_name', label: '省份名称', maxLength: 64 },
      { key: 'province_code', label: '省份编码', placeholder: '如：11', maxLength: 8 },
      { key: 'city_name', label: '地市名称', maxLength: 64 },
      { key: 'city_code', label: '地市编码', placeholder: '如：1101', maxLength: 8 },
      { key: 'district_name', label: '区县名称', maxLength: 64 },
      { key: 'district_code', label: '区县编码', placeholder: '如：110101', maxLength: 8 },
    ],
  },
  {
    title: '采集与标签',
    hint: '按业务约定填写采集优先级及分类。',
    fields: [
      { key: 'crawl_priority', label: '采集优先级', maxLength: 255 },
      { key: 'tag', label: '标签' },
      { key: 'data_type', label: '数据类型', hint: '综合填 0，政策填 1，新闻填 2；0、1 全爬，2 爬聚集板块。' },
    ],
  },
]
