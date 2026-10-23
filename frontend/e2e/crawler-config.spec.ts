import { expect, test, type Route } from '@playwright/test'

/** 爬虫配置统计：总览、近 12 周、分省情况（点省份看明细）、下载报告。接口全部用替身，省份和数量都只是样例。 */
const respond = (route: Route, data: unknown) => route.fulfill({ json: { code: 'OK', data } })

const MONDAYS = ['08-03', '08-10', '08-17', '08-24', '08-31', '09-07', '09-14', '09-21', '09-28', '10-05', '10-12', '10-19']
const WEEKLY_TOTALS = [0, 12, 0, 40, 0, 0, 88, 0, 0, 131, 203, 267]
// 每个省近 12 周的配置数，加起来等于上面每周的总数。
const PROVINCES: [string, number, number, number, number[]][] = [
  ['浙江省', 1302, 921, 0, [0, 0, 0, 10, 0, 0, 20, 0, 0, 30, 41, 66]],
  ['辽宁省', 980, 655, 2, [0, 12, 0, 0, 0, 0, 30, 0, 0, 25, 60, 59]],
  ['内蒙古自治区', 512, 330, 0, [0, 0, 0, 15, 0, 0, 0, 0, 0, 20, 35, 43]],
  ['吉林省', 640, 402, 0, [0, 0, 0, 0, 0, 0, 18, 0, 0, 16, 20, 39]],
  ['山西省', 588, 360, 1, [0, 0, 0, 15, 0, 0, 20, 0, 0, 10, 17, 34]],
  ['上海市', 588, 560, 0, [0, 0, 0, 0, 0, 0, 0, 0, 0, 30, 30, 13]],
  ['广东省', 1820, 1402, 3, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5]],
  ['海南省', 260, 120, 0, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3]],
  ['全国', 420, 388, 0, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3]],
  ['黑龙江省', 610, 233, 0, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]],
  ['江苏省', 1388, 1050, 0, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]],
  ['北京市', 640, 610, 0, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],
]

function report() {
  const provinces = PROVINCES.map(([name, total, online, abnormal, weekly]) => ({
    province_name: name, total, online, abnormal, pending: total - online - abnormal, new: weekly.at(-1) ?? 0,
    coverage: Math.round((online * 1000) / total) / 10, weekly,
  }))
  const sum = (key: 'total' | 'online' | 'pending' | 'abnormal' | 'new') => provinces.reduce((acc, row) => acc + row[key], 0)
  const totals = { total: sum('total'), online: sum('online'), pending: sum('pending'), abnormal: sum('abnormal'), new: sum('new') }
  let cumulative = 6400
  const trend = MONDAYS.map((monday, index) => {
    cumulative += WEEKLY_TOTALS[index] ?? 0
    return { week_from: `2026-${monday}`, week_to: `2026-${monday}`, new: WEEKLY_TOTALS[index] ?? 0, cumulative }
  })
  return {
    week_from: '2026-10-19', week_to: '2026-10-25', backfill_date: '2026-10-22', baseline: 6400, previous_new: 203,
    totals: { ...totals, coverage: Math.round((totals.online * 1000) / totals.total) / 10 },
    provinces, trend,
    new_sites: [
      { province_name: '浙江省', city_name: '杭州市', district_name: '', site_name: '杭州市数据资源管理局', site_code: '33010000012', url: 'https://example.gov.cn/a', crawler_status: '已爬', online_date: '2026-10-23' },
      { province_name: '辽宁省', city_name: '沈阳市', district_name: '', site_name: '沈阳市人民政府', site_code: '21010000104', url: 'https://example.gov.cn/b', crawler_status: '已爬', online_date: '2026-10-23' },
    ],
    last_sync: { status: 'success', rule_rows: 26135, rule_codes: 5998, blank_code_rows: 7776, matched: 5548, marked: 247, redated: 5100, unknown_codes: 450, finished_at: '2026-10-23T10:00:00Z' },
  }
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/csrf')) return respond(route, { csrf_token: 'test' })
    if (path.endsWith('/auth/refresh')) return respond(route, { access_token: 'test', expires_in: 3600, must_change_password: false })
    if (path.endsWith('/auth/me')) return respond(route, { id: 'leader', username: 'leader', display_name: '领导', status: 'active', roles: ['领导'] })
    if (path.endsWith('/auth/permissions')) {
      return respond(route, {
        resources: [{ code: 'policy.crawler_config', level: 'EXPORT' }],
        menus: [
          { id: 'policy', parent_id: null, title: '政策', route_name: null, resource_code: null, sort_order: 1 },
          { id: 'config', parent_id: 'policy', title: '爬虫配置统计', route_name: 'policy-crawler-config', resource_code: 'policy.crawler_config', sort_order: 1 },
        ],
      })
    }
    if (path.endsWith('/crawler-config/sync')) return respond(route, { active_run: null, last_run: null })
    if (path.endsWith('/crawler-config/report')) return respond(route, report())
    return respond(route, { items: [], total: 0, page: 1, page_size: 20 })
  })
})

test('从总览到分省再到明细：本周配置、近 12 周、各省、点省份看明细，能下载报告', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/policy/crawler-config')
  const overview = page.locator('.overview')
  await expect(overview.locator('.cell--week .cell__value')).toContainText('267')
  await expect(overview.locator('.cell--week')).toContainText('较上周 +64（上周 203）')
  await expect(page.getByRole('heading', { name: '每周配置数量' })).toBeVisible()
  await expect(page.getByRole('button', { name: '下载报告' })).toBeEnabled()
  await expect(page.getByRole('button', { name: '立即同步' })).toHaveCount(0)
  await expect(page.locator('.config__sync')).not.toContainText('没填网站编码')

  const table = page.locator('.provinces')
  await expect(table.locator('.el-table__body tr').first()).toContainText('浙江省')
  await expect(table.locator('.el-table__footer')).toContainText('总计')
  if (process.env.SHOT_DIR) {
    await page.screenshot({ path: `${process.env.SHOT_DIR}/page-top.png` })
    await table.screenshot({ path: `${process.env.SHOT_DIR}/provinces.png` })
  }

  await table.locator('.el-table__body tr').filter({ hasText: '辽宁省' }).first().click()
  const sites = page.locator('.sites')
  await expect(sites).toContainText('只看 辽宁省')
  await expect(sites.locator('.el-table__body tr')).toHaveCount(1)
  if (process.env.SHOT_DIR) await sites.screenshot({ path: `${process.env.SHOT_DIR}/sites.png` })
})
