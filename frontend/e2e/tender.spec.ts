import { expect, test, type Page, type Route } from '@playwright/test'

const respond = (route: Route, data: unknown) => route.fulfill({ json: { code: 'OK', data } })
const menus = [
  { id: 'tender', title: '招中标', parent_id: null, route_name: null, sort_order: 40 },
  ...['statistics', 'purchaser', 'winbid'].map((kind, index) => ({
    id: kind, title: ['招标统计分析', '招标基础数据', '中标基础数据'][index], parent_id: 'tender', route_name: `tender-${kind}`, sort_order: 41 + index,
  })),
]
const record = { id: '2005511121291911170', project_content_id: 'abc123456789012345678901234567890', project_name: '智慧园区信息化平台建设项目', purchaser: '某市公共服务中心', purchaser_provname: '北京市', purchaser_cityname: '北京市', purchaser_countyname: '朝阳区', project_status: '1', is_supp_scene: 0, public_date: '2026-11-11', collect_date: '2026-11-12', create_time: '2026-11-12 09:30:00', agency: '项目咨询有限公司', accepted_amount: '120万元' }
async function mockSource(page: Page) {
  const calls: string[] = []
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    calls.push(path + url.search)
    if (path.endsWith('/auth/csrf')) return respond(route, { csrf_token: 'test' })
    if (path.endsWith('/auth/refresh')) return respond(route, { access_token: 'test', expires_in: 3600, must_change_password: false })
    if (path.endsWith('/auth/me')) return respond(route, { id: 'viewer', username: 'viewer', display_name: '只读查看员', roles: [], must_change_password: false })
    if (path.endsWith('/auth/permissions')) return respond(route, { menus, resources: ['statistics', 'purchaser', 'winbid'].map(kind => ({ code: `tender.${kind}`, level: 'READ' })) })
    if (path.endsWith('/statistics/totals')) return respond(route, { state: 'ready', data: { total: 48000000, purchaser: 23968892, winbid: 24031108, as_of: '2026-11-12T10:00:00+08:00' } })
    if (path.endsWith('/statistics')) return respond(route, {
      date_from: '2026-11-06', date_to: '2026-11-12', as_of: '2026-11-12T10:00:00+08:00',
      daily: Array.from({ length: 7 }, (_, index) => ({ date: `2026-11-${String(index + 6).padStart(2, '0')}`, purchaser: 21000 + index * 200, winbid: 19000 + index * 300, tagged: 750, enriched: 750, scenario: 0 })),
      provinces: [{ province: '北京市', purchaser: 2000, winbid: 1800, tagged: 300, enriched: 300, scenario: 0 }],
    })
    if (path.endsWith('/content')) return respond(route, { html: '<h1>项目原始正文</h1><table><tr><td>预算</td><td>120万元</td></tr></table><script>parent.document.body.dataset.unsafe="yes"</script>' })
    if (path.endsWith('/count')) return respond(route, { state: 'ready', data: { total: 12345 } })
    const status = url.searchParams.get('project_status') || '1'
    const item = { ...record, project_status: status, project_name: status === '0' ? '未通过的原始智慧园区项目' : record.project_name }
    if (/\/tender\/(purchaser|winbid)\/\d+$/.test(path)) return respond(route, item)
    if (/\/tender\/(purchaser|winbid)$/.test(path)) return respond(route, { items: [item], has_more: true, page: 1, page_size: 20 })
    return respond(route, { items: [], total: 0 })
  })
  return calls
}

test('招中标：查询才切换数据视图，正文直接加载并隔离脚本', async ({ page }) => {
  const calls = await mockSource(page)
  await page.goto('/tender/purchaser')
  await expect(page.getByRole('link', { name: record.project_name, exact: true })).toBeVisible()
  await page.getByRole('button', { name: /展开筛选条件/ }).click()
  await page.getByRole('region', { name: '筛选条件' }).getByText('通过', { exact: true }).click()
  await page.getByRole('option', { name: '未通过' }).click()
  expect(calls.filter(url => url.includes('/tender/purchaser?')).every(url => !url.includes('project_status=0'))).toBe(true)
  await page.getByRole('button', { name: '查询', exact: true }).click()
  await expect(page.getByRole('link', { name: '未通过的原始智慧园区项目', exact: true })).toBeVisible()
  await page.getByRole('link', { name: '未通过的原始智慧园区项目', exact: true }).click()
  await expect(page.frameLocator('iframe').getByRole('heading', { name: '项目原始正文' })).toBeVisible()
  await expect(page.locator('iframe')).toHaveAttribute('sandbox', '')
  expect(await page.locator('body').getAttribute('data-unsafe')).toBeNull()
  await page.getByRole('link', { name: '返回列表', exact: true }).click()
  await expect(page.getByRole('link', { name: '未通过的原始智慧园区项目', exact: true })).toBeVisible()
})

test('招中标：从招标切到中标时重新加载对应列表', async ({ page }) => {
  const calls = await mockSource(page)
  await page.goto('/tender/purchaser')
  await page.getByRole('link', { name: '中标基础数据', exact: true }).click()
  await expect(page.getByRole('columnheader', { name: '中标金额', exact: true })).toBeAttached()
  expect(calls.some(url => url.includes('/tender/winbid?'))).toBe(true)
})

for (const width of [1024, 1280, 1440, 1920, 2560]) {
  test(`招中标：${width}px 统计与列表布局`, async ({ page }) => {
    await mockSource(page)
    await page.setViewportSize({ width, height: 1000 })
    await page.goto('/tender/statistics')
    await expect(page.getByText('48,000,000', { exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: '每天数据接入情况' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    if (width === 1440) {
      await page.screenshot({ path: test.info().outputPath('tender-statistics.png'), fullPage: true })
      await page.getByRole('heading', { name: '每日统计明细' }).scrollIntoViewIfNeeded()
      await page.screenshot({ path: test.info().outputPath('tender-statistics-bottom.png'), fullPage: true })
    }
    await page.getByRole('link', { name: '中标基础数据', exact: true }).click()
    await expect(page.getByRole('link', { name: record.project_name, exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await expect(page.getByRole('button', { name: '下一页', exact: true })).toBeEnabled()
    if (width === 1440) await page.screenshot({ path: test.info().outputPath('tender-list.png'), fullPage: true })
  })
}
