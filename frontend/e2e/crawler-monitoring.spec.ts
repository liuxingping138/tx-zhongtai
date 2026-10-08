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

test('爬虫监测：概览、筛选、翻页和任务详情', async ({ page }) => {
  test.skip(!currentAdminPassword(), '缺少 ADMIN_PASSWORD')
  const problems = trackProblems(page)

  await loginAdmin(page, '/policy/crawler-monitoring')

  await expect(page.getByRole('heading', { name: '爬虫监测', exact: true })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByRole('navigation', { name: '子模块导航' }).getByRole('link', { name: '爬虫监测', exact: true })).toBeVisible()
  await expect(page.getByText('昨日采集', { exact: true })).toBeVisible()
  await expect(page.getByText('异常任务', { exact: true })).toBeVisible()
  await expect(page.getByText('健康占比', { exact: true })).toBeVisible()
  await expect(page.getByText(/更新于/)).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '网站名称' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '停更天数' })).toBeVisible()
  await expect(page.locator('.overview .el-loading-mask')).toHaveCount(0)

  const trend90 = page.waitForResponse(
    (response) => response.url().includes('/crawler-monitoring/overview') && response.url().includes('trend_days=90') && response.ok(),
  )
  // Element Plus 的 radio 本体被同名 span 盖住，点可见文字。
  await page.locator('.el-radio-button').filter({ hasText: '近90天' }).click()
  await trend90
  await expect(page.getByRole('heading', { name: '日采集量趋势' })).toBeVisible()

  const filtered = page.waitForResponse(
    (response) => response.url().includes('/crawler-monitoring/tasks?') && response.url().includes('health_status=broken') && response.ok(),
  )
  await page.locator('.legend').getByRole('button', { name: /断爬/ }).click()
  const filteredResponse = await filtered
  const filteredBody = await filteredResponse.json()
  expect(filteredBody.data.total).toBeGreaterThan(0)
  await expect(page.getByRole('cell', { name: '断爬', exact: true }).first()).toBeVisible()
  await expect(page.locator('.el-loading-mask')).toHaveCount(0)

  await page.locator('.business-table__desktop .record-title').first().scrollIntoViewIfNeeded()
  const hit = await page.evaluate(() => {
    const button = document.querySelector('.business-table__desktop .record-title')
    if (!(button instanceof HTMLElement)) return { ok: false, reason: 'missing' }
    const rect = button.getBoundingClientRect()
    const x = rect.left + rect.width / 2
    const y = rect.top + Math.min(rect.height / 2, 12)
    const top = document.elementFromPoint(x, y)
    const covered = top !== button && !button.contains(top)
    return {
      ok: !covered,
      reason: covered ? top?.className || top?.tagName || 'covered' : 'clear',
      rowTop: Math.round(rect.top),
      rowHeight: Math.round(rect.height),
    }
  })
  expect(hit.ok, `第一行网站名称点不到，挡住它的是 ${hit.reason}`).toBe(true)

  const exportResponse = page.waitForResponse((response) => response.url().includes('/crawler-monitoring/tasks/export') && response.ok())
  await page.getByRole('button', { name: '下载 Excel', exact: true }).click()
  expect(new URL((await exportResponse).url()).searchParams.get('health_status')).toBe('broken')
  const tableHeight = await page.locator('.list-page__results').evaluate((el) => el.getBoundingClientRect().height)
  expect(tableHeight).toBeGreaterThanOrEqual(440)

  const detail = page.waitForResponse(
    (response) => response.url().includes('/crawler-monitoring/tasks/detail') && response.ok(),
  )
  await page.locator('.business-table__desktop .record-title').first().click()
  await detail
  const drawer = page.locator('.el-drawer')
  await expect(drawer.getByRole('heading', { name: '任务详情' })).toBeVisible()
  await expect(drawer.getByRole('heading', { name: '近 90 天采集量' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()

  const reset = page.waitForResponse((response) => {
    if (!response.url().includes('/crawler-monitoring/tasks?') || !response.ok()) return false
    const url = new URL(response.url())
    return !url.searchParams.has('health_status') && url.searchParams.get('page') === '1'
  })
  await page.getByRole('button', { name: '重置', exact: true }).click()
  const resetBody = await (await reset).json()
  expect(resetBody.data.total).toBeGreaterThan(filteredBody.data.total)

  const page2 = page.waitForResponse(
    (response) => response.url().includes('/crawler-monitoring/tasks?') && response.url().includes('page=2') && response.ok(),
  )
  await page.locator('.el-pager li').filter({ hasText: /^2$/ }).click()
  await page2

  expect(problems.pageErrors).toEqual([])
  expect(problems.httpErrors).toEqual([])
})
