import type { TenderKind } from '@/api/tender'
import type { DataColumn } from '@/components/dataColumns'

const common: DataColumn[] = [
  { prop: 'project_name', label: '项目名称', minWidth: 300, grow: 2 },
  { prop: 'purchaser_provname', label: '招标单位省份', width: 130 },
  { prop: 'purchaser_cityname', label: '招标单位市', width: 130 },
  { prop: 'purchaser_countyname', label: '招标单位区县', width: 140 },
  { prop: 'purchaser', label: '招标单位名称', minWidth: 220 },
  { prop: 'purchaser_address', label: '招标公司地址', minWidth: 240 },
  { prop: 'agency', label: '代理机构', minWidth: 220 },
  { prop: 'public_date', label: '发布时间', width: 180 },
  { prop: 'from_url', label: '发布链接', minWidth: 220, link: true },
  { prop: 'first_indty_name', label: '一级行业名称', width: 180 },
  { prop: 'second_indty_name', label: '二级行业名称', width: 180 },
  { prop: 'third_indty_name', label: '三级行业名称', width: 180 },
  { prop: 'first_scene_name', label: '一级场景', width: 180 },
  { prop: 'second_scene_name', label: '二级场景', width: 180 },
  { prop: 'third_scene_name', label: '三级场景', width: 180 },
]
export function tenderColumns(kind: TenderKind): DataColumn[] {
  const specific: DataColumn[] = kind === 'winbid' ? [
    { prop: 'winbid', label: '中标单位名称', minWidth: 220 },
    { prop: 'accepted_amount', label: '中标金额', width: 150 },
    { prop: 'bid_type', label: '招标方式', width: 140 },
  ] : [
    { prop: 'open_date', label: '开标时间', width: 180 },
    { prop: 'end_date', label: '结束时间', width: 180 },
  ]
  return [...common.slice(0, 7), ...specific, ...common.slice(7),
    { prop: 'project_status', label: '项目状态', width: 160 },
    { prop: 'is_supp_scene', label: '是否补充场景', width: 130 },
    { prop: 'project_code', label: '项目编号', width: 180 },
    { prop: 'project_content_id', label: '项目ID', width: 280 },
    { prop: 'collect_date', label: '采集时间', width: 140 },
    { prop: 'create_time', label: '入库时间', width: 190 },
  ]
}
export const REGIONS = [
  { key: 'purchaser_provname', label: '省份' },
  { key: 'purchaser_cityname', label: '地市' },
  { key: 'purchaser_countyname', label: '区县' },
] as const
export const DATES = [
  { key: 'collect_date', label: '采集时间' },
  { key: 'public_date', label: '发布时间' },
  { key: 'create_time', label: '入库时间' },
] as const
export function initialQuery() {
  return {
    project_name: '', project_content_id: '', project_status: '0',
    purchaser_provname: [] as string[], purchaser_cityname: [] as string[], purchaser_countyname: [] as string[],
    is_supp_scene: [] as string[], collect_date_from: '', collect_date_to: '',
    public_date_from: '', public_date_to: '', create_time_from: '', create_time_to: '', page: 1, page_size: 20,
  }
}
export type TenderQuery = ReturnType<typeof initialQuery>
