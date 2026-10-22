import { expect, test } from '@playwright/test'

import { currentAdminPassword, loginAdmin } from './adminSession'

test.use({ viewport: { width: 1440, height: 900 } })

// 只验收保存设置，不点「立即执行」：P6 不配大模型密钥，也不连源库。
test('政策 AI 打标：改每批条数后能保存，读取进度这类只读字段不会被提交', async ({ page }) => {
  test.skip(!currentAdminPassword(), '缺少 ADMIN_PASSWORD')
  await loginAdmin(page, '/system/scheduler')

  const panel = page.getByRole('region', { name: '政策 AI 打标' })
  await expect(panel).toBeVisible({ timeout: 20_000 })
  const batch = panel.locator('.el-form-item').filter({ hasText: '每批打标条数' }).locator('input')
  await batch.fill('10')
  await batch.blur()

  const saved = page.waitForResponse(r => r.url().endsWith('/ai-tagging/config') && r.request().method() === 'PUT')
  await panel.getByRole('button', { name: '保存设置' }).click()
  const response = await saved
  expect(response.status()).toBe(200)
  expect(Object.keys(response.request().postDataJSON() as object)).not.toContain('cursor_content_id')
  await expect(page.getByText('设置已保存')).toBeVisible()
  await expect(batch).toHaveValue('10')
})
