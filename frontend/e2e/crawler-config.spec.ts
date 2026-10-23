import { expect, test, type Route } from '@playwright/test'

/** 爬虫配置统计：本周各省配置网站数量（和每周给领导的那张表一致）、每周进度、累计和下载报告。接口全部用替身。 */
const respond = (route: Route, data: unknown) => route.fulfill({ json: { code: 'OK', data } })

// 用户每周给领导看的那张表（省份、配置网站数量），总计 267。
const WEEK = { 广东省: 5, 海南省: 3, 黑龙江省: 1, 吉林省: 39, 江苏省: 1, 辽宁省: 59, 内蒙古自治区: 43, 全国: 3, 山西省: 34, 上海市: 13, 浙江省: 66 } as Record<string, number>
const TOTALS: [string, number, number, number][] = [
  ['浙江省', 1302, 921, 0], ['辽宁省', 980, 655, 2], ['内蒙古自治区', 512, 330, 0], ['吉林省', 640, 402, 0], ['山西省', 588, 360, 1],
  ['上海市', 588, 560, 0], ['广东省', 1820, 1402, 3], ['海南省', 260, 120, 0], ['全国', 420, 388, 0], ['黑龙江省', 610, 233, 0],
  ['江苏省', 1388, 1050, 0], ['山东省', 1510, 1064, 0], ['北京市', 640, 610, 0],
]

function report(counted: boolean) {
  const provinces = TOTALS.map(([name, total, online, abnormal]) => {
    const added = counted ? WEEK[name] ?? 0 : 0
    return { province_name: name, total, online, abnormal, pending: total - online - abnormal, new: added, coverage: Math.round((online * 1000) / total) / 10, weekly: counted ? [added] : [] }
  })
  const sum = (key: 'total' | 'online' | 'pending' | 'abnormal' | 'new') => provinces.reduce((acc, row) => acc + row[key], 0)
  const totals = { total: sum('total'), online: sum('online'), pending: sum('pending'), abnormal: sum('abnormal'), new: sum('new') }
  return {
    week_from: counted ? '2026-10-19' : '2026-10-12',
    week_to: counted ? '2026-10-25' : '2026-10-18',
    report_start: '2026-10-23',
    counted,
    baseline: 11984,
    previous_new: null,
    totals: { ...totals, coverage: Math.round((totals.online * 1000) / totals.total) / 10 },
    provinces,
    trend: counted ? [{ week_from: '2026-10-19', week_to: '2026-10-25', new: totals.new, cumulative: 11984 + totals.new }] : [],
    new_sites: counted
      ? [{ province_name: '浙江省', city_name: '杭州市', district_name: '', site_name: '杭州市数据资源管理局', site_code: '33010000012', url: 'https://example.gov.cn', crawler_status: '已爬', online_date: '2026-10-23' }]
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

test('领导一打开就看到本周各省配置网站数量和总计，并能下载报告', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/policy/crawler-config')
  const hero = page.locator('.hero')
  await expect(hero.getByRole('heading')).toHaveText('本周配置网站数量')
  await expect(hero.locator('strong')).toHaveText('267')
  await expect(hero.locator('.hero__list li').first()).toContainText('浙江省66')
  await expect(hero.locator('.hero__list li')).toHaveCount(11)
  await expect(hero).toContainText('10月23日起统计')
  await expect(page.getByRole('button', { name: '下载报告' })).toBeEnabled()
  await expect(page.getByRole('button', { name: '立即同步' })).toHaveCount(0)
  // 领导只看更新时间，规则表的对账细节不给他看。
  await expect(page.locator('.config__sync')).not.toContainText('没填网站编码')
  if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/counted.png`, fullPage: true })

  const provinces = page.locator('.provinces')
  await expect(provinces.locator('.el-table__body tr').first()).toContainText('浙江省')
  await expect(provinces.locator('.el-table__footer')).toContainText('总计')
  if (process.env.SHOT_DIR) await provinces.screenshot({ path: `${process.env.SHOT_DIR}/provinces.png` })
  await provinces.locator('.el-radio-button').filter({ hasText: '每周配置数' }).click()
  await expect(page.locator('.weekly thead th.is-selected')).toHaveText('本周')
  if (process.env.SHOT_DIR) await provinces.screenshot({ path: `${process.env.SHOT_DIR}/weekly.png` })
})

test('统计起点之前的周：不显示配置数量，说明从哪天开始统计', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/policy/crawler-config')
  await page.getByRole('button', { name: '上一周' }).click()
  const hero = page.locator('.hero')
  await expect(hero.locator('strong')).toHaveText('—')
  await expect(hero).toContainText('每周配置数量从 10月23日开始统计')
  if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/before-start.png`, fullPage: true })
})
