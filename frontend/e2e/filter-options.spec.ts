import { expect, test, type Page, type Route } from '@playwright/test'

const resources = ['policy.sources', 'system.audit']
const respond = (route: Route, data: unknown) => route.fulfill({ json: { code: 'OK', data } })

/** 省份候选完整（truncated=false），网站名称候选被截断（truncated=true）。 */
const OPTIONS = {
  options: {
    site_name: { items: ['打底站点A', '打底站点B'], truncated: true },
    province_name: { items: ['北京市', '江苏省', '广东省'], truncated: false },
    city_name: { items: ['打底地市'], truncated: true },
    tag: { items: ['标签甲'], truncated: true },
    crawl_priority: { items: ['1', '2'], truncated: false },
  },
  city_by_province: { 江苏省: ['南京市', '苏州市'] },
}

/** 记录每次 options/search 请求，供断言防抖与请求次数。 */
type SearchLog = { field: string; q: string }

async function mockSession(page: Page, searches: SearchLog[], hold?: { route?: Route }) {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (path.endsWith('/auth/csrf')) return respond(route, { csrf_token: 'test' })
    if (path.endsWith('/auth/refresh')) return respond(route, { access_token: 'test', expires_in: 3600, must_change_password: false })
    if (path.endsWith('/auth/me')) return respond(route, { id: 'admin', username: 'admin', display_name: '测试管理员', status: 'active', roles: ['超级管理员'] })
    if (path.endsWith('/auth/permissions')) return respond(route, { resources: resources.map(code => ({ code, level: 'FULL' })), menus: [] })
    if (path.endsWith('/options/search')) {
      const field = url.searchParams.get('field') ?? ''
      const q = url.searchParams.get('q') ?? ''
      searches.push({ field, q })
      if (hold && !hold.route) {
        hold.route = route // 第一次搜索先扣住，用于竞态验证
        return
      }
      return respond(route, { items: [`搜索命中:${q}`] })
    }
    if (path.endsWith('/options')) return respond(route, OPTIONS)
    return respond(route, { items: [], total: 0, page: 1, page_size: 20 })
  })
}

/** 打开某个筛选项的下拉。多选模式下输入框很窄且被占位文字盖住，像用户一样点整个选择框。 */
async function openFilter(page: Page, label: string) {
  const item = page.locator('.el-form-item').filter({ hasText: label }).first()
  await item.locator('.el-select__wrapper').first().click()
  return item
}

test('候选完整的字段本地过滤，不发服务端搜索请求', async ({ page }) => {
  const searches: SearchLog[] = []
  await mockSession(page, searches)
  await page.goto('/policy/sources')

  const item = await openFilter(page, '省份')
  await expect(page.getByRole('option', { name: '北京市', exact: true })).toBeVisible()
  await expect(page.getByRole('option', { name: '江苏省', exact: true })).toBeVisible()

  await item.locator('input').first().fill('江苏')
  await expect(page.getByRole('option', { name: '江苏省', exact: true })).toBeVisible()
  await expect(page.getByRole('option', { name: '北京市', exact: true })).toHaveCount(0)

  await page.waitForLoadState('networkidle')
  expect(searches).toHaveLength(0) // 全程没有发过搜索请求
})

test('候选被截断的字段走服务端搜索，且输入防抖只发一次', async ({ page }) => {
  const searches: SearchLog[] = []
  await mockSession(page, searches)
  await page.goto('/policy/sources')

  const item = await openFilter(page, '网站名称')
  // 未输入关键词时先看到打底候选
  await expect(page.getByRole('option', { name: '打底站点A', exact: true })).toBeVisible()

  const input = item.locator('input').first()
  const searchResponse = page.waitForResponse(res => res.url().includes('/options/search'))
  await input.pressSequentially('北京市', { delay: 40 })
  await searchResponse

  await expect(page.getByRole('option', { name: '搜索命中:北京市', exact: true })).toBeVisible()
  await page.waitForLoadState('networkidle')
  expect(searches).toHaveLength(1) // 三次按键被防抖合并成一次
  expect(searches[0]).toEqual({ field: 'site_name', q: '北京市' })
})

test('先发出的搜索响应晚到时不覆盖后一次的结果', async ({ page }) => {
  const searches: SearchLog[] = []
  const hold: { route?: Route } = {}
  await mockSession(page, searches, hold)
  await page.goto('/policy/sources')

  const item = await openFilter(page, '网站名称')
  const input = item.locator('input').first()

  await input.fill('旧')
  await expect.poll(() => hold.route !== undefined).toBe(true)

  await input.fill('新')
  await expect(page.getByRole('option', { name: '搜索命中:新', exact: true })).toBeVisible()

  // 让第一次请求此刻才返回
  const staleResponse = page.waitForResponse(res => res.url().includes('/options/search') && res.url().includes(encodeURIComponent('旧')))
  await respond(hold.route!, { items: ['搜索命中:旧'] })
  await staleResponse

  await expect(page.getByRole('option', { name: '搜索命中:新', exact: true })).toBeVisible()
  await expect(page.getByRole('option', { name: '搜索命中:旧', exact: true })).toHaveCount(0)
})

test('清空关键词后回到打底候选，不残留上一次搜索结果', async ({ page }) => {
  const searches: SearchLog[] = []
  await mockSession(page, searches)
  await page.goto('/policy/sources')

  const item = await openFilter(page, '网站名称')
  const input = item.locator('input').first()
  await input.fill('北京')
  await expect(page.getByRole('option', { name: '搜索命中:北京', exact: true })).toBeVisible()

  await input.fill('')
  await expect(page.getByRole('option', { name: '打底站点A', exact: true })).toBeVisible()
  await expect(page.getByRole('option', { name: '搜索命中:北京', exact: true })).toHaveCount(0)
})

test('从 URL 回填的筛选值即使不在候选里也要显示出来', async ({ page }) => {
  const searches: SearchLog[] = []
  await mockSession(page, searches)
  // 该值不在打底候选 ['打底站点A','打底站点B'] 里
  await page.goto('/policy/sources?site_name=' + encodeURIComponent('郴州人力资源和社会保障局'))

  // Element Plus 把选中值渲染在独立元素里，input 只是搜索框，所以断言展示文本。
  const item = page.locator('.el-form-item').filter({ hasText: '网站名称' }).first()
  await expect(item).toContainText('郴州人力资源和社会保障局')
})

test('选了省份后地市用该省列表，不走服务端搜索', async ({ page }) => {
  const searches: SearchLog[] = []
  await mockSession(page, searches)
  await page.goto('/policy/sources')

  const province = await openFilter(page, '省份')
  await page.getByRole('option', { name: '江苏省', exact: true }).click()

  await openFilter(page, '地市')
  await expect(page.getByRole('option', { name: '南京市', exact: true })).toBeVisible()
  await expect(page.getByRole('option', { name: '苏州市', exact: true })).toBeVisible()
  await expect(page.getByRole('option', { name: '打底地市', exact: true })).toHaveCount(0)

  await page.waitForLoadState('networkidle')
  expect(searches.filter(s => s.field === 'city_name')).toHaveLength(0)
  await expect(province).toBeVisible()
})

test('操作日志的筛选项走同一套机制', async ({ page }) => {
  const searches: SearchLog[] = []
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (path.endsWith('/auth/csrf')) return respond(route, { csrf_token: 'test' })
    if (path.endsWith('/auth/refresh')) return respond(route, { access_token: 'test', expires_in: 3600, must_change_password: false })
    if (path.endsWith('/auth/me')) return respond(route, { id: 'admin', username: 'admin', display_name: '测试管理员', status: 'active', roles: ['超级管理员'] })
    if (path.endsWith('/auth/permissions')) return respond(route, { resources: resources.map(code => ({ code, level: 'FULL' })), menus: [] })
    if (path.endsWith('/options/search')) {
      searches.push({ field: url.searchParams.get('field') ?? '', q: url.searchParams.get('q') ?? '' })
      return respond(route, { items: ['搜索命中:张三'] })
    }
    if (path.endsWith('/options')) {
      return respond(route, { options: { actor_name: { items: ['李四'], truncated: true }, module_code: { items: ['policy.sources'], truncated: false }, action_code: { items: ['export'], truncated: false } } })
    }
    return respond(route, { items: [], total: 0, page: 1, page_size: 20 })
  })
  await page.goto('/system/audit')

  const item = await openFilter(page, '人员')
  await item.locator('input').first().fill('张三')
  await expect(page.getByRole('option', { name: '搜索命中:张三', exact: true })).toBeVisible()
  expect(searches[0]?.field).toBe('actor_name')
})
