import { expect, test } from '@playwright/test'

import { loginAdmin } from './adminSession'

test('码表两级目录与智库知识库主流程', async ({ page }) => {
  await loginAdmin(page)

  // 1. 验证「码表管理」包含「数据字典（政策类型/行业场景/省市区）」与「智库码表（暂无二级）」
  await page.getByRole('navigation', { name: '一级模块' }).getByRole('link', { name: '码表管理', exact: true }).click()
  const sidebar = page.getByRole('navigation', { name: '子模块导航' })
  await expect(sidebar.getByRole('button', { name: '数据字典' })).toBeVisible()
  await expect(sidebar.getByRole('button', { name: '智库码表' })).toBeVisible()
  await expect(sidebar.getByRole('link', { name: '政策类型码表', exact: true })).toBeVisible()
  await expect(sidebar.getByRole('link', { name: '行业场景码表', exact: true })).toBeVisible()
  await expect(sidebar.getByRole('link', { name: '省市区码表', exact: true })).toBeVisible()
  await expect(sidebar.getByText('暂无码表')).toBeVisible()

  // 2. 进入「智库 -> 知识库」验证 1,448 条全量历史数据加载、操作日志、独立详情页查看与编辑
  await page.getByRole('navigation', { name: '一级模块' }).getByRole('link', { name: '智库', exact: true }).click()
  await expect(page).toHaveURL(/\/thinktank\/knowledge$/)
  await expect(page.getByRole('heading', { name: '智库知识库' })).toBeVisible()
  await expect(page.getByText(/共\s*1,448\s*条/)).toBeVisible({ timeout: 15_000 })

  const firstRow = page.locator('.el-table__body tbody tr').first()
  await expect(firstRow).toBeVisible()

  // 打开单文件操作日志抽屉（包含历史迁移的 7,648 条日志）
  await firstRow.getByRole('button', { name: /更多/ }).click()
  await page.getByRole('menuitem', { name: '操作日志' }).click()
  const logsDialog = page.getByRole('dialog', { name: /操作日志/ })
  await expect(logsDialog).toBeVisible()
  await logsDialog.locator('.el-drawer__close-btn').click()
  await expect(logsDialog).toBeHidden()

  // 点击预览跳转到独立详情预览工作台（含上一条/下一条翻页与内联编辑）
  await firstRow.getByRole('link', { name: '预览', exact: true }).click()
  await expect(page).toHaveURL(/\/thinktank\/knowledge\/.+/)
  await expect(page.getByRole('button', { name: '基本信息', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /收藏/ })).toBeVisible()

  // 3. 验证「角色与权限」中「菜单权限」与「智库数据权限」已独立拆分
  await page.goto('/system/roles')
  await expect(page.getByRole('tab', { name: '菜单权限' })).toBeVisible()
  const dataScopeTab = page.getByRole('tab', { name: '智库数据权限' })
  await expect(dataScopeTab).toBeVisible()
  await dataScopeTab.click()
  await expect(page.getByRole('heading', { name: '知识库 · 文件类型范围' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '知识库 · 行业类型范围' })).toBeVisible()
})
