import { expect, test } from '@playwright/test'

const menus = [
  { id: 'policy', parent_id: null, title: '政策', route_name: null, sort_order: 1 },
  { id: 'sources', parent_id: 'policy', title: '信源管理', route_name: 'policy-sources', resource_code: 'policy.sources', sort_order: 1 },
  { id: 'types', parent_id: null, title: '政策类型码表', route_name: 'codebook-policy-types', resource_code: 'codebook.policy_types', sort_order: 2 },
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

test('desktop collapse persists across reload and offers grouped and direct navigation', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/')
  const sidebar = page.locator('#desktop-navigation')
  await expect(sidebar).toHaveCSS('width', '220px')
  await page.getByRole('button', { name: '收起侧栏', exact: true }).click()
  await expect(sidebar).toHaveCSS('width', '64px')
  await expect(sidebar.getByRole('button', { name: '测试管理员，打开账号菜单' })).toBeVisible()
  await expect(sidebar.getByText('超级管理员', { exact: true })).toHaveCount(0)
  await page.reload()
  await expect(sidebar).toHaveCSS('width', '64px')
  await sidebar.getByRole('menuitem', { name: '政策', exact: true }).hover()
  await page.getByRole('menuitem', { name: '信源管理', exact: true }).click()
  await expect(page).toHaveURL(/\/policy\/sources$/)
  await expect(sidebar.locator('.has-active-child')).toHaveCount(1)
  await sidebar.getByRole('menuitem', { name: '政策类型码表', exact: true }).click()
  await expect(page).toHaveURL(/\/codebook\/policy-types$/)
  const toggle = page.getByRole('button', { name: '展开侧栏', exact: true })
  await toggle.focus()
  await page.keyboard.press('Enter')
  await expect(sidebar).toHaveCSS('width', '220px')
  await expect(sidebar.getByRole('button', { name: '测试管理员，打开账号菜单' })).toBeVisible()
  await expect(sidebar.getByText('超级管理员', { exact: true })).toBeVisible()
})

test('mobile drawer navigates, closes with Escape and restores focus', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(page.locator('#desktop-navigation')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await expect(page.getByRole('banner').getByRole('button', { name: '测试管理员，打开账号菜单' })).toBeVisible()
  const toggle = page.getByRole('button', { name: '打开导航菜单', exact: true })
  await toggle.click()
  const drawer = page.getByRole('dialog', { name: '导航菜单', exact: true })
  await expect(drawer).toBeVisible()
  await expect(drawer.getByRole('button', { name: '测试管理员，打开账号菜单' })).toBeVisible()
  await expect(drawer.getByText('超级管理员', { exact: true })).toBeVisible()
  await drawer.getByRole('menuitem', { name: '政策', exact: true }).click()
  await drawer.getByRole('menuitem', { name: '信源管理', exact: true }).click()
  await expect(page).toHaveURL(/\/policy\/sources$/)
  await expect(drawer).toBeHidden()
  await toggle.click()
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
  await expect(toggle).toBeFocused()
  await toggle.click()
  await page.getByRole('button', { name: '关闭导航菜单', exact: true }).click()
  await expect(drawer).toBeHidden()
})

test('viewport changes close the drawer and preserve desktop choice', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/')
  await page.getByRole('button', { name: '收起侧栏', exact: true }).click()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: '打开导航菜单', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '导航菜单' })).toBeVisible()
  await page.setViewportSize({ width: 960, height: 800 })
  await expect(page.getByRole('dialog', { name: '导航菜单' })).toHaveCount(0)
  await expect(page.locator('#desktop-navigation')).toHaveCSS('width', '64px')
  await page.getByRole('button', { name: '展开侧栏', exact: true }).click()
  await expect(page.locator('#desktop-navigation')).toHaveCSS('width', '190px')
})
