import { expect, test, type Page, type Response } from '@playwright/test'

import { currentAdminPassword, loginAdmin } from './adminSession'

test.use({ viewport: { width: 1440, height: 900 } })

function trackProblems(page: Page) {
  const pageErrors: string[] = []
  const httpErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('response', (response: Response) => {
    const url = response.url()
    if (!url.includes('/api/') || response.status() < 400) return
    // 打开登录页时会先试一次续期，没有会话就是 401，不是页面故障。
    if (response.status() === 401 && url.includes('/auth/refresh')) return
    httpErrors.push(`${response.status()} ${url}`)
  })
  return { pageErrors, httpErrors }
}

const sitesResponse = (predicate: (url: URL) => boolean) => (response: Response) => {
  if (!response.url().includes('/crawler-monitoring-v2/sites?') || !response.ok()) return false
  return predicate(new URL(response.url()))
}

test('爬虫监测：卡片、筛选联动与导出', async ({ page }) => {
  test.skip(!currentAdminPassword(), '缺少 ADMIN_PASSWORD')
  const problems = trackProblems(page)

  await loginAdmin(page, '/policy/crawler-monitoring-v2')

  await expect(page.getByRole('heading', { name: '爬虫监测', exact: true })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByRole('navigation', { name: '子模块导航' }).getByRole('link', { name: '爬虫监测', exact: true })).toBeVisible()
  for (const label of ['网站总数', '数据总量', '近 7 天采集']) {
    await expect(page.locator('.card-label').filter({ hasText: label })).toBeVisible()
  }
  await expect(page.getByText(/更新于/)).toBeVisible()
  await expect(page.locator('.overview .el-loading-mask')).toHaveCount(0)

  // 状态卡片即筛选：点「停更」只看停更网站，导出带同样条件。
  const stale = page.waitForResponse(sitesResponse((url) => url.searchParams.get('status') === 'stale'))
  await page.locator('.card-status').filter({ hasText: '停更' }).click()
  const staleBody = await (await stale).json()
  expect(staleBody.data.total).toBeGreaterThan(0)
  await expect(page.locator('.card-status.selected')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('cell', { name: '停更', exact: true }).first()).toBeVisible()

  const exportResponse = page.waitForResponse(
    (response) => response.url().includes('/crawler-monitoring-v2/sites/export') && response.ok(),
  )
  await page.getByRole('button', { name: '下载 Excel', exact: true }).click()
  expect(new URL((await exportResponse).url()).searchParams.get('status')).toBe('stale')

  // 再次点击取消状态筛选。
  const cleared = page.waitForResponse(sitesResponse((url) => !url.searchParams.has('status')))
  await page.locator('.card-status').filter({ hasText: '停更' }).click()
  const allBody = await (await cleared).json()
  expect(allBody.data.total).toBeGreaterThan(staleBody.data.total)

  const tableHeight = await page.locator('.list-page__results').evaluate((el) => el.getBoundingClientRect().height)
  expect(tableHeight).toBeGreaterThanOrEqual(440)

  await page.locator('.business-table__desktop .record-title').first().click()
  const drawer = page.locator('.el-drawer')
  await expect(drawer.getByRole('heading', { name: '网站详情' })).toBeVisible()
  await expect(drawer.getByText('最新入库时间')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()

  expect(problems.pageErrors).toEqual([])
  expect(problems.httpErrors).toEqual([])
})

test('爬虫监测：趋势切换范围，健康结构点分类筛选明细', async ({ page }) => {
  test.skip(!currentAdminPassword(), '缺少 ADMIN_PASSWORD')
  const problems = trackProblems(page)

  const firstTrend = page.waitForResponse(
    (response) => response.url().includes('/crawler-monitoring-v2/trend?days=90') && response.ok(),
  )
  await loginAdmin(page, '/policy/crawler-monitoring-v2')
  await firstTrend
  for (const name of ['采集趋势', '健康结构', '省份分布']) {
    await expect(page.getByRole('heading', { name, exact: true })).toBeVisible({ timeout: 20_000 })
  }
  await expect(page.getByRole('img', { name: /^采集趋势图：/ }).locator('canvas')).toBeVisible()
  await expect(page.getByRole('img', { name: /^省份分布：/ }).locator('canvas')).toBeVisible()

  const monthly = page.waitForResponse(
    (response) => response.url().includes('/crawler-monitoring-v2/trend?days=30') && response.ok(),
  )
  await page.getByRole('radiogroup', { name: '趋势时间范围' }).getByText('近 30 天', { exact: true }).click()
  expect((await (await monthly).json()).data.items).toHaveLength(30)

  const stale = page.waitForResponse(sitesResponse((url) => url.searchParams.get('status') === 'stale'))
  await page.locator('.legend button').filter({ hasText: '近期停更' }).click()
  await stale
  await expect(page.locator('.legend button').filter({ hasText: '近期停更' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('.card-status').filter({ hasText: '停更' })).toHaveAttribute('aria-pressed', 'true')

  expect(problems.pageErrors).toEqual([])
  expect(problems.httpErrors).toEqual([])
})

test('爬虫监测：同一字段多选按「或」查询，导出带同样的多个值', async ({ page }) => {
  test.skip(!currentAdminPassword(), '缺少 ADMIN_PASSWORD')
  const problems = trackProblems(page)
  const provinces = ['海南省', '甘肃省']

  await loginAdmin(page, '/policy/crawler-monitoring-v2')
  await expect(page.getByRole('heading', { name: '爬虫监测', exact: true })).toBeVisible({ timeout: 20_000 })

  const field = page.locator('.filter-bar .el-form-item').filter({ hasText: '省份' }).first()
  for (const province of provinces) {
    await field.locator('.el-select__wrapper').click()
    await field.locator('input').first().fill(province)
    await page.getByRole('option', { name: province, exact: true }).click()
  }
  await page.keyboard.press('Escape')
  await expect(page.getByText('条件已改，点击查询后生效', { exact: true })).toBeVisible()

  const filtered = page.waitForResponse(
    sitesResponse((url) => url.searchParams.getAll('province_name').sort().join() === [...provinces].sort().join()),
  )
  await page.getByRole('button', { name: '查询', exact: true }).click()
  const body = await (await filtered).json()
  expect(body.data.total).toBeGreaterThan(0)
  const seen = new Set(body.data.items.map((item: { province_name: string }) => item.province_name))
  expect([...seen].every((name) => provinces.includes(name as string))).toBe(true)
  // 已选值折叠成首个标签加「+1」，一个字段只算一项筛选。
  await expect(page.getByText('已筛选 1 项', { exact: true })).toBeVisible()

  const exportResponse = page.waitForResponse(
    (response) => response.url().includes('/crawler-monitoring-v2/sites/export') && response.ok(),
  )
  await page.getByRole('button', { name: '下载 Excel', exact: true }).click()
  expect(new URL((await exportResponse).url()).searchParams.getAll('province_name').sort()).toEqual([...provinces].sort())

  // 刷新后从地址栏恢复两个值，仍然是同一个查询。
  const restored = page.waitForResponse(sitesResponse((url) => url.searchParams.getAll('province_name').length === 2))
  await page.reload()
  expect((await (await restored).json()).data.total).toBe(body.data.total)

  expect(problems.pageErrors).toEqual([])
  expect(problems.httpErrors).toEqual([])
})
