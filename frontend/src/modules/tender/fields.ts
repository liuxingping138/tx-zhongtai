import type { TenderKind } from '@/api/tender'
import type { DataColumn } from '@/components/dataColumns'
import type { EditorGroup } from '@/components/editorGroups'

export function tenderColumns(kind: TenderKind): DataColumn[] {
  const coreSpecific: DataColumn[] = kind === 'winbid'
    ? [
        { prop: 'winbid', label: '中标单位名称', minWidth: 220 },
        { prop: 'accepted_amount', label: '中标金额（万元）', width: 150 },
        { prop: 'bid_type', label: '招标方式', width: 140 },
      ]
    : [
        { prop: 'budget_fund', label: '预算金额（万元）', width: 150 },
      ]
  const timeSpecific: DataColumn[] = kind === 'purchaser'
    ? [
        { prop: 'open_date', label: '开标时间', width: 180 },
        { prop: 'end_date', label: '结束时间', width: 180 },
      ]
    : []
  return [
    { prop: 'project_name', label: '项目名称', minWidth: 300, grow: 2 },
    { prop: 'project_status', label: '项目状态', width: 110 },
    { prop: 'public_date', label: '发布时间', width: 180 },
    { prop: 'purchaser_provname', label: '招标单位省份', width: 130 },
    { prop: 'purchaser_cityname', label: '招标单位市', width: 130 },
    { prop: 'purchaser_countyname', label: '招标单位区县', width: 140 },
    ...coreSpecific,
    { prop: 'purchaser', label: '招标单位名称', minWidth: 220 },
    { prop: 'agency', label: '代理机构', minWidth: 220 },
    ...timeSpecific,
    { prop: 'first_indty_name', label: '一级行业名称', width: 180 },
    { prop: 'second_indty_name', label: '二级行业名称', width: 180 },
    { prop: 'third_indty_name', label: '三级行业名称', width: 180 },
    { prop: 'first_scene_name', label: '一级场景', width: 180 },
    { prop: 'second_scene_name', label: '二级场景', width: 180 },
    { prop: 'third_scene_name', label: '三级场景', width: 180 },
    { prop: 'is_supp_scene', label: '是否补充场景', width: 130 },
    { prop: 'purchaser_address', label: '招标公司地址', minWidth: 240 },
    { prop: 'from_url', label: '发布链接', minWidth: 220, link: true },
    { prop: 'project_code', label: '项目编号', width: 180 },
    { prop: 'project_content_id', label: '项目ID', width: 280 },
    { prop: 'collect_date', label: '采集时间', width: 140 },
    { prop: 'create_time', label: '入库时间', width: 190 },
  ]
}

export function tenderDetailGroups(kind: TenderKind): EditorGroup[] {
  const coreSpecific = kind === 'winbid'
    ? [
        { key: 'bid_type', label: '招标方式' },
        { key: 'accepted_amount', label: '中标金额（万元）' },
      ]
    : [
        { key: 'budget_fund', label: '预算金额（万元）' },
        { key: 'open_date', label: '开标时间' },
        { key: 'end_date', label: '结束时间' },
      ]
  const partySpecific = kind === 'winbid' ? [{ key: 'winbid', label: '中标单位名称', long: true }] : []
  return [
    {
      title: '项目核心信息',
      hint: '',
      fields: [
        { key: 'project_name', label: '项目名称', long: true },
        { key: 'project_status', label: '项目状态' },
        { key: 'project_code', label: '项目编号' },
        { key: 'public_date', label: '发布时间' },
        ...coreSpecific,
        { key: 'from_url', label: '发布链接', long: true },
      ],
    },
    {
      title: '招中标主体与地区',
      hint: '',
      fields: [
        { key: 'purchaser', label: '招标单位名称', long: true },
        ...partySpecific,
        { key: 'purchaser_provname', label: '招标单位省份' },
        { key: 'purchaser_cityname', label: '招标单位市' },
        { key: 'purchaser_countyname', label: '招标单位区县' },
        { key: 'agency', label: '代理机构' },
        { key: 'purchaser_address', label: '招标公司地址', long: true },
      ],
    },
    {
      title: '行业与场景标签',
      hint: '',
      fields: [
        { key: 'first_indty_name', label: '一级行业名称' },
        { key: 'second_indty_name', label: '二级行业名称' },
        { key: 'third_indty_name', label: '三级行业名称' },
        { key: 'is_supp_scene', label: '是否补充场景' },
        { key: 'first_scene_name', label: '一级场景' },
        { key: 'second_scene_name', label: '二级场景' },
        { key: 'third_scene_name', label: '三级场景' },
      ],
    },
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
    project_name: '', project_content_id: '', project_status: '1',
    purchaser_provname: [] as string[], purchaser_cityname: [] as string[], purchaser_countyname: [] as string[],
    is_supp_scene: [] as string[], collect_date_from: '', collect_date_to: '',
    public_date_from: '', public_date_to: '', create_time_from: '', create_time_to: '', page: 1, page_size: 20,
  }
}
export const MAX_NAME_FILTER_DAYS = 366

export function hasBoundedDateRange(query: TenderQuery): boolean {
  for (const field of DATES) {
    const from = query[`${field.key}_from`]
    const to = query[`${field.key}_to`]
    if (!from || !to) continue
    const days = Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000)
    if (days >= 0 && days < MAX_NAME_FILTER_DAYS) return true
  }
  return false
}

export function validateTenderSearch(query: TenderQuery): string | null {
  if (query.project_name.trim() && !hasBoundedDateRange(query)) {
    return '按项目名称查询时，请先选择完整的日期范围（建议选择采集时间，且跨度不超过 366 天）'
  }
  return null
}

export type TenderQuery = ReturnType<typeof initialQuery>
