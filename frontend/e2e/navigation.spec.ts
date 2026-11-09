import { expect, test } from '@playwright/test'

const menus = [
  { id: 'policy', parent_id: null, title: '政策', route_name: null, sort_order: 1 },
  { id: 'sources', parent_id: 'policy', title: '信源管理', route_name: 'policy-sources', resource_code: 'policy.sources', sort_order: 1 },
  { id: 'codebook', parent_id: null, title: '码表管理', route_name: null, sort_order: 2 },
  { id: 'types', parent_id: 'codebook', title: '政策类型码表', route_name: 'codebook-policy-types', resource_code: 'codebook.policy_types', sort_order: 1 },
]

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    const data = path.endsWith('/auth/csrf') ? { csrf_token: 'test' }
      : path.endsWith('/auth/refresh') ? { access_token: 'test', expires_in: 3600, must_change_password: false }
        : path.endsWith('/auth/me') ? { id: 'admin', username: 'admin', display_name: '测试管理员', status: 'active', roles: ['超级管理员'] }
          : path.endsWith('/auth/permissions') ? { menus, resources: ['policy.sources', 'codebook.policy_types'].map(code => ({ code, level: 'FULL' })) }
            : path.endsWith('/options') ? {} : { items: [], total: 0, page: 1, page_size: 20 }
    return route.fulfill({ json: { code: 'OK', data } })
  })
})

test('desktop uses the top modules and the side list, with the account at the bottom', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/')
  const rail = page.locator('.workspace-rail')
  const domains = page.getByRole('navigation', { name: '一级模块' })
  const modules = page.getByRole('navigation', { name: '子模块导航' })
  await expect(rail).toHaveCSS('width', '216px')
  await expect(domains.getByRole('link', { name: '政策', exact: true })).toHaveAttribute('aria-current', 'true')
  await expect(modules.getByRole('link', { name: '信源管理', exact: true })).toBeVisible()
  await expect(rail.getByRole('button', { name: '测试管理员，打开账号菜单' })).toBeVisible()
  await expect(rail.getByText('超级管理员', { exact: true })).toBeVisible()

  await modules.getByRole('link', { name: '信源管理', exact: true }).click()
  await expect(page).toHaveURL(/\/policy\/sources$/)
  await expect(modules.getByRole('link', { name: '信源管理', exact: true })).toHaveAttribute('aria-current', 'page')

  await domains.getByRole('link', { name: '码表管理', exact: true }).click()
  await expect(page).toHaveURL(/\/codebook\/policy-types$/)
  await expect(domains.getByRole('link', { name: '码表管理', exact: true })).toHaveAttribute('aria-current', 'true')
  await expect(modules.getByRole('link', { name: '政策类型码表', exact: true })).toHaveAttribute('aria-current', 'page')
})

test('1024px keeps the same navigation and narrows the side list', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/')
  await page.setViewportSize({ width: 1024, height: 800 })
  const rail = page.locator('.workspace-rail')
  await expect(rail).toHaveCSS('width', '200px')
  await expect(page.getByRole('dialog', { name: '导航菜单' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '收起侧栏' })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('navigation', { name: '一级模块' }).getByRole('link', { name: '码表管理', exact: true }).click()
  await expect(page).toHaveURL(/\/codebook\/policy-types$/)
  await expect(page.getByRole('navigation', { name: '子模块导航' }).getByRole('link', { name: '政策类型码表', exact: true })).toBeVisible()
})
