import { expect, test, type Route } from '@playwright/test'

/** 爬虫配置统计：一句话结论、按周配置数量、上周各省配置排行（弹窗）、分省爬虫状态、下载报告。接口全部用替身，省份和数量都只是样例。 */
const respond = (route: Route, data: unknown) => route.fulfill({ json: { code: 'OK', data } })

const MONDAYS = ['08-10', '08-17', '08-24', '08-31', '09-07', '09-14', '09-21', '09-28', '10-05', '10-12', '10-19', '10-26']
const WEEKLY_TOTALS = [12, 0, 40, 0, 0, 88, 0, 0, 131, 203, 267, 0]
// 上周各省配置数，加起来 267。
const CONFIGURED: [string, number][] = [
  ['浙江省', 66], ['辽宁省', 59], ['内蒙古自治区', 43], ['吉林省', 39], ['山西省', 34], ['上海市', 13],
  ['广东省', 5], ['全国', 3], ['海南省', 3], ['黑龙江省', 1], ['江苏省', 1],
]
const STATUS: [string, number, number, number][] = [
  ['北京市', 640, 610, 0], ['上海市', 588, 560, 0], ['浙江省', 1302, 921, 0], ['辽宁省', 980, 655, 2],
]

function report() {
  const status = STATUS.map(([name, total, online, abnormal]) => ({ province_name: name, total, online, abnormal, pending: total - online - abnormal }))
  const sum = (key: 'total' | 'online' | 'pending' | 'abnormal') => status.reduce((acc, row) => acc + row[key], 0)
  const totals = { total: sum('total'), online: sum('online'), pending: sum('pending'), abnormal: sum('abnormal') }
  return {
    unit: 'week', period_from: '2026-10-19', period_to: '2026-10-25', current_from: '2026-10-26',
    new: 267, previous_new: 203, backfill_date: '2026-10-22', baseline: 6400,
    periods: MONDAYS.map((monday, index) => ({ period_from: `2026-${monday}`, period_to: `2026-${monday}`, new: WEEKLY_TOTALS[index] ?? 0 })),
    provinces: CONFIGURED.map(([name, count]) => ({ province_name: name, new: count })),
    status,
    totals: { ...totals, coverage: Math.round((totals.online * 1000) / totals.total) / 10 },
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

test('默认看上周：一句话结论、各期和各省配置数量、分省爬虫状态，能下载报告', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/policy/crawler-config')
  await expect(page.locator('.headline')).toContainText('上周新配置 267 个网站，分布在 11 个省，浙江省最多（66 个），较上一周 +64')
  await expect(page.locator('.card--main .card-value')).toHaveText('267')
  await expect(page.getByRole('heading', { name: '配置数量' })).toBeVisible()
  // 各省配置是点柱子或「上周各省明细」弹出的排行，复制表格在弹窗里。
  await page.getByRole('button', { name: '上周各省明细' }).click()
  const provinces = page.locator('.province-dialog')
  await expect(provinces.getByRole('heading', { name: '上周各省配置' })).toBeVisible()
  await expect(provinces).toContainText('11 个省份有配置')
  await expect(provinces.locator('.ranking li').first()).toContainText('浙江省')
  await expect(provinces.getByRole('button', { name: '复制表格' })).toBeEnabled()
  await page.keyboard.press('Escape')
  await expect(provinces).toBeHidden()
  await expect(page.getByRole('button', { name: '下载报告' })).toBeEnabled()
  await expect(page.getByRole('button', { name: '立即同步' })).toHaveCount(0)
  if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/page.png`, fullPage: true })

  await expect(page.getByRole('heading', { name: '分省爬虫状态' })).toBeVisible()
  await page.getByRole('radio', { name: '表格' }).dispatchEvent('click')
  const table = page.locator('.status-table')
  await expect(table.locator('.el-table__body tr').first()).toContainText('北京市')
  await expect(table.locator('.el-table__footer')).toContainText('总计')
  if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/table.png` })
})
