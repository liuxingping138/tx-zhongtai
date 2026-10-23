import { expect, test, type Route } from '@playwright/test'

/** 爬虫配置统计：给领导看的结论、每周进度、分省进度和下载报告。接口全部用替身。 */
const respond = (route: Route, data: unknown) => route.fulfill({ json: { code: 'OK', data } })

const PROVINCES = [
  ['广东省', 1820, 1402, 3], ['山东省', 1510, 1064, 0], ['江苏省', 1388, 1050, 1], ['浙江省', 1302, 921, 0],
  ['河南省', 1201, 488, 2], ['四川省', 1104, 812, 0], ['湖北省', 980, 655, 0], ['河北省', 905, 402, 0],
  ['湖南省', 862, 590, 0], ['安徽省', 801, 533, 0], ['福建省', 760, 489, 0], ['北京市', 640, 610, 0],
  ['上海市', 588, 560, 0], ['陕西省', 560, 233, 0], ['云南省', 512, 199, 0], ['国央企', 420, 388, 0],
  ['（未填省份）', 37, 0, 0],
] as const

function report(counted: boolean) {
  const provinces = PROVINCES.map(([name, total, online, abnormal], index) => ({
    province_name: name, total, online, abnormal, pending: total - online - abnormal,
    new: counted ? [12, 0, 8, 5, 0, 3][index] ?? 0 : 0, coverage: Math.round((online * 1000) / total) / 10,
    weekly: counted ? [[9, 6, 12], [4, 3, 0], [5, 2, 8], [3, 4, 5], [6, 0, 0], [2, 3, 3], [3, 2, 0], [1, 1, 0]][index] ?? [0, 0, 0] : [],
  }))
  const sum = (key: 'total' | 'online' | 'pending' | 'abnormal' | 'new') => provinces.reduce((acc, row) => acc + row[key], 0)
  const totals = { total: sum('total'), online: sum('online'), pending: sum('pending'), abnormal: sum('abnormal'), new: sum('new') }
  return {
    week_from: counted ? '2026-11-09' : '2026-10-19',
    week_to: counted ? '2026-11-15' : '2026-10-25',
    report_start: '2026-10-26',
    counted,
    baseline: 11984,
    previous_new: counted ? 21 : null,
    totals: { ...totals, coverage: Math.round((totals.online * 1000) / totals.total) / 10 },
    provinces,
    trend: counted
      ? [
          { week_from: '2026-10-26', week_to: '2026-11-01', new: 35, cumulative: 12019 },
          { week_from: '2026-11-02', week_to: '2026-11-08', new: 21, cumulative: 12040 },
          { week_from: '2026-11-09', week_to: '2026-11-15', new: totals.new, cumulative: 12040 + totals.new },
        ]
      : [],
    new_sites: counted
      ? [{ province_name: '广东省', city_name: '广州市', district_name: '', site_name: '广州市数据局', site_code: '44010000012', url: 'https://example.gov.cn', crawler_status: '已爬', online_date: '2026-11-13' }]
      : [],
    last_sync: { status: 'success', rule_rows: 26135, rule_codes: 5998, blank_code_rows: 7776, matched: 5548, marked: 247, unknown_codes: 450, finished_at: '2026-10-23T08:39:02Z' },
  }
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url())
    const path = url.pathname
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
    if (path.endsWith('/crawler-config/report')) return respond(route, report(!url.searchParams.has('week')))
    return respond(route, { items: [], total: 0, page: 1, page_size: 20 })
  })
})

test('领导一打开就看到已配置多少、本周新配置多少，并能下载报告', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/policy/crawler-config')
  const headline = page.locator('.config__headline')
  await expect(headline).toContainText('截至今天，已配置爬虫栏目 10,396 个，占信源栏目的 67.6%')
  await expect(headline).toContainText('本周新增 28 个，较上周 +7')
  await expect(headline).toContainText('6 个栏目异常待核对')
  await expect(page.getByRole('heading', { name: '每周配置进度' })).toBeVisible()
  await expect(page.locator('.province').first()).toContainText('广东省')
  await expect(page.getByRole('button', { name: '下载报告' })).toBeEnabled()
  await expect(page.getByRole('button', { name: '立即同步' })).toHaveCount(0)
  // 领导只看更新时间，规则表的对账细节不给他看。
  await expect(page.locator('.config__sync')).not.toContainText('没填网站编码')
  if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/counted.png`, fullPage: true })

  await page.locator('.el-radio-button').filter({ hasText: '每周配置数' }).click()
  await expect(page.locator('.weekly tbody tr').first()).toContainText('广东省')
  await expect(page.locator('.weekly thead th.is-selected')).toHaveText('本周')
  if (process.env.SHOT_DIR) await page.locator('.provinces').screenshot({ path: `${process.env.SHOT_DIR}/weekly.png` })
  await page.locator('.el-radio-button').filter({ hasText: '表格' }).click()
  await expect(page.getByRole('cell', { name: '合计' })).toBeVisible()
})

test('统计起点之前的周：不显示新增，说明从哪周开始统计', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/policy/crawler-config')
  await page.getByRole('button', { name: '上一周' }).click()
  const headline = page.locator('.config__headline')
  await expect(headline).toContainText('截至 10月25日')
  await expect(headline).toContainText('每周新增从 10月26日那周开始统计')
  await expect(page.locator('.stat--new .stat__value')).toHaveText('—')
  if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/before-start.png`, fullPage: true })
})
