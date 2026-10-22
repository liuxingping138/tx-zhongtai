import { expect, test } from '@playwright/test'

import { currentAdminPassword, loginAdmin } from './adminSession'

test.use({ viewport: { width: 1440, height: 900 } })

// 只验收列表和设置，不点「立即执行」：P6 不配大模型密钥，也不连源库。
test('政策 AI 打标：三个任务各占一行，在设置抽屉里改每批条数能保存', async ({ page }) => {
  test.skip(!currentAdminPassword(), '缺少 ADMIN_PASSWORD')
  await loginAdmin(page, '/system/scheduler')

  const rows = page.locator('.el-table__body tr')
  await expect(rows.filter({ hasText: '政策类型判断' })).toBeVisible({ timeout: 20_000 })
  for (const name of ['政策解读', '政策市场机会']) await expect(rows.filter({ hasText: name })).toBeVisible()
  // 原来列表下面那块「政策 AI 打标」大面板已经去掉。
  await expect(page.getByRole('heading', { name: '政策 AI 打标' })).toHaveCount(0)

  await rows.filter({ hasText: '政策类型判断' }).getByRole('button', { name: '设置', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: '设置 · 政策类型判断' })
  await expect(drawer.getByText('从哪天的采集数据开始')).toBeVisible()
  const batch = drawer.locator('.el-form-item').filter({ hasText: '每批条数' }).locator('input')
  await batch.fill('10')
  await batch.blur()

  const saved = page.waitForResponse(r => r.url().endsWith('/ai-tagging/tasks/type') && r.request().method() === 'PUT')
  await drawer.getByRole('button', { name: '保存设置' }).click()
  const response = await saved
  expect(response.status()).toBe(200)
  expect(Object.keys(response.request().postDataJSON() as object)).not.toContain('cursor_content_id')
  await expect(page.getByText('设置已保存')).toBeVisible()
  await expect(drawer).toBeHidden()

  // 解读任务没有读取进度，设置里不出现起始日期。
  await rows.filter({ hasText: '政策解读' }).getByRole('button', { name: '设置', exact: true }).click()
  const interpret = page.getByRole('dialog', { name: '设置 · 政策解读' })
  await expect(interpret.getByText('使用的模板')).toBeVisible()
  await expect(interpret.getByText('从哪天的采集数据开始')).toHaveCount(0)
})
