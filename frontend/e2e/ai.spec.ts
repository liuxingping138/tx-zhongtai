import { expect, test } from '@playwright/test'
import path from 'node:path'

import { currentAdminPassword, loginAdmin } from './adminSession'

test.use({ viewport: { width: 1440, height: 900 } })

// P6 不配大模型密钥：这里只验收模板、附件、变量插入、权限入口和「未配置密钥」的提示，不真的产生调用费用。
const workbook = path.join(import.meta.dirname, 'fixtures', 'ai-template.xlsx')

test('AI提问：新建模板、上传 Excel、@ 插入列名，批量和对话页说明密钥未配置', async ({ page }) => {
  test.skip(!currentAdminPassword(), '缺少 ADMIN_PASSWORD')
  const title = `e2e 提问 ${Date.now()}`
  await loginAdmin(page, '/ai/prompts')

  await expect(page.getByRole('navigation', { name: '一级模块' }).getByText('AI提问')).toBeVisible({ timeout: 20_000 })
  await page.getByRole('button', { name: '新建' }).click()
  await page.getByRole('textbox', { name: '提示词标题' }).fill(title)
  const content = page.getByRole('textbox', { name: '提示词内容' })
  await content.fill('企业：')
  await page.getByRole('textbox', { name: '新增输出字段' }).fill('行业|场景')
  await page.getByRole('button', { name: '追加格式要求' }).click()
  await expect(content).toHaveValue(/2、返回字段：行业、场景/)
  await expect(page.getByText('未保存')).toBeVisible()
  const created = page.waitForResponse(r => r.url().endsWith('/api/v1/ai/prompts') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '保存模板' }).click()
  expect((await created).status()).toBe(201)
  await expect(page.getByRole('list', { name: '提示词模板' }).getByText(title)).toBeVisible()

  const uploaded = page.waitForResponse(r => r.url().includes('/files/excel') && r.request().method() === 'POST')
  await page.locator('input[type=file][accept=".xlsx"]').setInputFiles(workbook)
  expect((await uploaded).status()).toBe(200)
  await expect(page.getByText('ai-template.xlsx')).toBeVisible()
  await expect(page.getByText('（2 行数据）')).toBeVisible()

  // 光标放到「企业：」后面输入 @，从候选里选列名。
  await content.click()
  await content.press('ControlOrMeta+Home')
  await content.press('End')
  await content.pressSequentially('@企')
  await page.getByRole('option', { name: '@【企业名称】' }).click()
  await expect(content).toHaveValue(/^企业：@【企业名称】/)

  await page.goto('/ai/batch-runs')
  await page.getByRole('list', { name: '提示词模板' }).getByText(title).click()
  await expect(page.getByText('ai-template.xlsx（2 行）')).toBeVisible()
  await expect(page.getByText(/接口密钥未配置|请选择运行使用的模型/)).toBeVisible()
  await expect(page.getByRole('button', { name: '运行全部' })).toBeDisabled()
  await expect(page.getByRole('heading', { name: '批量提问历史' })).toBeVisible()

  await page.goto('/ai/chat')
  // Element Plus 的输入框被选中项那层盖住，要点外层包裹元素才能展开。
  await page.locator('.model-picker .el-select__wrapper').click()
  await expect(page.getByRole('option').filter({ hasText: '未配置密钥' }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: '发送' })).toBeDisabled()

  // 清理：删掉本用例建的模板。
  await page.goto('/ai/prompts')
  await page.getByRole('list', { name: '提示词模板' }).getByText(title).click()
  await page.getByRole('button', { name: '删除模板' }).click()
  await page.getByRole('dialog').getByRole('button', { name: '删除' }).click()
  await expect(page.getByRole('list', { name: '提示词模板' }).getByText(title)).toHaveCount(0)
})
