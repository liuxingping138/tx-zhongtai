import { expect, test, type Page, type Route } from '@playwright/test'

const resources = ['policy.sources', 'policy.base_tags', 'policy.interpretations', 'codebook.policy_types', 'codebook.scenarios', 'codebook.area_codes', 'system.users', 'system.roles', 'system.permissions', 'system.audit']
const role = (id: string) => ({ id, name: `角色${id}`, code: `role_${id}`, status: 'active', version: 1, is_builtin: false })
const respond = (route: Route, data: unknown) => route.fulfill({ json: { code: 'OK', data } })

async function mockSession(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/csrf')) return respond(route, { csrf_token: 'test' })
    if (path.endsWith('/auth/refresh')) return respond(route, { access_token: 'test', expires_in: 3600, must_change_password: false })
    if (path.endsWith('/auth/me')) return respond(route, { id: 'admin', username: 'admin', display_name: '测试管理员', status: 'active', roles: ['超级管理员'] })
    if (path.endsWith('/auth/permissions')) return respond(route, { resources: resources.map(code => ({ code, level: 'FULL' })), menus: [] })
    if (path.endsWith('/options')) return respond(route, {})
    return respond(route, { items: [], total: 0, page: 1, page_size: 20 })
  })
}

test.beforeEach(async ({ page }) => { await mockSession(page) })

for (const module of ['policy/sources', 'codebook/policy-types', 'system/users']) {
  test(`${module}: late response does not overwrite a newer query`, async ({ page }) => {
    let first: Route | undefined
    let calls = 0
    await page.route(`**/api/v1/${module}?**`, async route => {
      const url = new URL(route.request().url())
      if (url.searchParams.get('page_size') === '100') return respond(route, { items: [], total: 0 })
      calls += 1
      if (calls === 1) { first = route; return }
      return respond(route, { items: [{ id: 'new', site_name: '最新结果', type_name: '最新结果', username: '最新结果' }], total: 1 })
    })
    await page.goto(`/${module}`)
    await expect.poll(() => first !== undefined).toBe(true)
    await page.getByRole('button', { name: '查询', exact: true }).click()
    await expect(page.getByText('最新结果', { exact: true })).toBeVisible()
    await respond(first!, { items: [{ id: 'old', site_name: '过期结果', type_name: '过期结果', username: '过期结果' }], total: 1 })
    await expect(page.getByText('最新结果', { exact: true })).toBeVisible()
    await expect(page.getByText('过期结果', { exact: true })).toHaveCount(0)
  })
}

test('audit: clearing the date range still submits the query', async ({ page }) => {
  await page.goto('/system/audit')
  const inputs = page.locator('.el-range-input')
  await inputs.nth(0).fill('2026-09-01 00:00:00')
  await inputs.nth(1).fill('2026-09-18 23:59:59')
  await inputs.nth(1).press('Enter')
  await page.getByRole('heading', { name: '操作日志' }).click()
  await page.locator('.el-date-editor').hover()
  // 清除图标只在 hover 时出现且带过渡动画，click() 等不到 stable；
  // force 点击又会因为指针移开而丢掉 hover，真正生效的是直接派发 click 事件。
  await page.locator('.el-range__close-icon').dispatchEvent('click')
  const request = page.waitForRequest(r => r.url().includes('/audit/events?'))
  await page.getByRole('button', { name: '查询', exact: true }).click()
  const url = new URL((await request).url())
  expect(url.searchParams.has('occurred_from')).toBe(false)
  expect(url.searchParams.has('occurred_to')).toBe(false)
})

test('roles: changing status resets pagination', async ({ page }) => {
  await page.route('**/api/v1/system/roles?**', route => respond(route, { items: [role('1')], total: 45 }))
  await page.goto('/system/roles')
  await page.locator('.el-pager li').filter({ hasText: /^2$/ }).click()
  await page.locator('.filter-bar .el-select').click()
  const request = page.waitForRequest(r => r.url().includes('status=disabled'))
  await page.getByRole('option', { name: '停用', exact: true }).click()
  expect(new URL((await request).url()).searchParams.get('page')).toBe('1')
})

test('permissions: role load failure keeps selection; saving locks inputs and role switching', async ({ page }) => {
  await page.route('**/api/v1/system/roles?**', route => respond(route, { items: [role('1'), role('2')], total: 2 }))
  await page.route('**/api/v1/system/resources', route => respond(route, { tree: [{ id: 'r', code: 'policy.sources', name: '信源', node_type: 'resource', published: true }] }))
  let saving: Route | undefined
  await page.route('**/api/v1/system/roles/*/grants', route => {
    if (route.request().method() === 'PUT') { saving = route; return }
    if (route.request().url().includes('/2/')) return route.fulfill({ status: 500, json: { message: '加载失败' } })
    return respond(route, { role: role('1'), grants: [] })
  })
  await page.goto('/system/permissions')
  await page.getByRole('button', { name: /角色2/ }).click()
  await expect(page.locator('.iam-role.is-active')).toContainText('角色1')
  await page.locator('.el-radio-button').filter({ hasText: '只读' }).click()
  await page.getByRole('button', { name: '保存授权', exact: true }).click()
  await page.locator('.el-message-box').getByRole('button', { name: /确定|确认/ }).click()
  await expect.poll(() => saving !== undefined).toBe(true)
  await expect(page.getByRole('button', { name: /角色2/ })).toBeDisabled()
  await expect(page.getByRole('radio', { name: '可管理', exact: true })).toBeDisabled()
  await respond(saving!, { role: { ...role('1'), version: 2 }, grants: [{ resource_code: 'policy.sources', level: 'READ' }] })
  await expect(page.getByText('1 项待保存')).toHaveCount(0)
})


test('permissions: initial load failure shows a persistent error with a working retry', async ({ page }) => {
  // 原来初次加载失败只弹一个会消失的 toast，页面空着且没有重试入口，只能刷整页。
  await page.route('**/api/v1/system/resources', route => respond(route, { tree: [] }))
  let attempts = 0
  await page.route('**/api/v1/system/roles?**', route => {
    attempts += 1
    if (attempts === 1) return route.fulfill({ status: 503, json: { message: '授权服务暂时不可用' } })
    return respond(route, { items: [role('1')], total: 1 })
  })
  await page.route('**/api/v1/system/roles/*/grants', route => respond(route, { role: role('1'), grants: [] }))

  await page.goto('/system/permissions')
  const error = page.getByRole('alert').filter({ hasText: '暂时无法加载授权' })
  await expect(error).toBeVisible()
  await expect(error).toContainText('授权服务暂时不可用')

  await error.getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.getByRole('button', { name: /角色1/ })).toBeVisible()
  await expect(page.getByText('暂时无法加载授权')).toHaveCount(0)
})

test('permissions: includes roles after the first 100', async ({ page }) => {
  await page.route('**/api/v1/system/roles?**', route => {
    const second = new URL(route.request().url()).searchParams.get('page') === '2'
    return respond(route, { items: second ? [role('101')] : Array.from({ length: 100 }, (_, i) => role(String(i + 1))), total: 101 })
  })
  await page.route('**/api/v1/system/resources', route => respond(route, { tree: [] }))
  await page.route('**/api/v1/system/roles/*/grants', route => respond(route, { role: role('1'), grants: [] }))
  await page.goto('/system/permissions')
  await page.getByPlaceholder('搜索名称 / 编码').fill('role_101')
  await expect(page.getByRole('button', { name: /角色101/ })).toBeVisible()
})
