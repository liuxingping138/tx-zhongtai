import { expect, test } from '@playwright/test'

import { currentAdminPassword, loginAdmin } from './adminSession'

test('登录后可见系统模块，刷新与第二标签页保持会话', async ({ page, context }) => {
  test.skip(!currentAdminPassword(), '缺少 ADMIN_PASSWORD')
  await loginAdmin(page)
  await page.getByRole('navigation', { name: '一级模块' }).getByRole('link', { name: '系统管理', exact: true }).click()
  await expect(page.getByRole('navigation', { name: '子模块导航' }).getByRole('link', { name: '操作日志', exact: true })).toBeVisible()

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
