import { expect, test } from '@playwright/test'

const username = process.env.ADMIN_USERNAME || 'p6admin'
const password = process.env.ADMIN_PASSWORD || ''

test('登录后可见系统模块，刷新与第二标签页保持会话', async ({ page, context }) => {
  test.skip(!password, '缺少 ADMIN_PASSWORD')
  await page.goto('/login')
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码').fill(password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page.getByText('欢迎', { exact: false })).toBeVisible({ timeout: 20_000 })
  await page.getByRole('menuitem', { name: '系统管理' }).click()
  await expect(page.getByRole('menuitem', { name: '操作日志' })).toBeVisible()

  await page.goto('/system/audit')
  await expect(page.getByRole('button', { name: '查询' })).toBeVisible()

  const second = await context.newPage()
  await second.goto('/system/users')
  await expect(second.getByRole('columnheader', { name: '用户名' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: '查询' })).toBeVisible()
  await second.close()
})

test('未登录不能进用户管理', async ({ page }) => {
  await page.goto('/system/users')
  await expect(page).toHaveURL(/login/)
})
