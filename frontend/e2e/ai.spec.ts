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
  await page.getByRole('textbox', { name: '模板标题' }).fill(title)
  const content = page.getByRole('textbox', { name: '提示词内容' })
  await content.fill('企业：')
  // 输出字段是标签输入：竖线断开成两个字段，回车收下最后一个。
  const fields = page.getByRole('textbox', { name: '输出字段' })
  await fields.fill('行业|场景')
  await fields.press('Enter')
  await page.getByRole('button', { name: '把格式要求追加到提示词' }).click()
  await expect(content).toHaveValue(/2、返回字段：行业、场景/)
  await expect(page.getByText('未保存')).toBeVisible()
  const created = page.waitForResponse(r => r.url().endsWith('/api/v1/ai/prompts') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '保存', exact: true }).click()
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
  const runCard = page.getByRole('region', { name: '运行' })
  await expect(runCard.getByRole('heading', { name: title })).toBeVisible()
  await expect(runCard.getByText('2 行', { exact: true })).toBeVisible()
  await expect(page.getByText(/接口密钥未配置|请选择运行使用的模型/)).toBeVisible()
  await expect(page.getByRole('button', { name: /^运行全部/ })).toBeDisabled()
  await expect(page.getByRole('heading', { name: '批量提问历史' })).toBeVisible()

  await page.goto('/ai/chat')
  // Element Plus 的输入框被选中项那层盖住，要点外层包裹元素才能展开。
  await page.locator('.chat__model .el-select__wrapper').click()
  await expect(page.getByRole('option').filter({ hasText: '未配置密钥' }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: '发送' })).toBeDisabled()

  // 清理：删掉本用例建的模板。
  await page.goto('/ai/prompts')
  await page.getByRole('list', { name: '提示词模板' }).getByText(title).click()
  await page.getByRole('button', { name: '删除模板' }).click()
  await page.getByRole('dialog').getByRole('button', { name: '删除' }).click()
  await expect(page.getByRole('list', { name: '提示词模板' }).getByText(title)).toHaveCount(0)
})

test('政策类模板：按草稿提示能不能用于三个打标任务，从数据库取测试数据说清楚取不到的原因', async ({ page }) => {
  test.skip(!currentAdminPassword(), '缺少 ADMIN_PASSWORD')
  const title = `e2e 政策模板 ${Date.now()}`
  await loginAdmin(page, '/ai/prompts')
  await expect(page.getByRole('navigation', { name: '一级模块' }).getByText('AI提问')).toBeVisible({ timeout: 20_000 })
  await page.getByRole('button', { name: '新建' }).click()
  await page.getByRole('textbox', { name: '模板标题' }).fill(title)
  // 类型选政策：Element Plus 下拉点外层包裹再选项。
  await page.locator('.studio__category .el-select__wrapper').click()
  await page.getByRole('option', { name: '政策类', exact: true }).click()
  const content = page.getByRole('textbox', { name: '提示词内容' })
  await content.fill('判断政策类型：@【政策标题】@【政策正文】')
  const fields = page.getByRole('textbox', { name: '输出字段' })
  await fields.fill('政策类型名称')
  await fields.press('Enter')

  const fit = page.getByRole('list', { name: '定时任务适配' })
  await expect(fit.getByRole('listitem').filter({ hasText: '政策类型判断' })).toContainText('可以用')
  // 类型判断模板本来不是给解读用的：显示灰色「不适用」，不标红。
  await expect(fit.getByRole('listitem').filter({ hasText: '政策解读' })).toContainText('不适用')
  // 改草稿立刻重新检查：用了打标任务不提供的列。
  await content.fill('判断：@【企业名称】@【政策正文】')
  await expect(fit.getByRole('listitem').filter({ hasText: '政策类型判断' })).toContainText('用了这个任务不提供的列：@【企业名称】')
  await content.fill('判断政策类型：@【政策标题】@【政策正文】')

  const created = page.waitForResponse(r => r.url().endsWith('/api/v1/ai/prompts') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  expect((await created).status()).toBe(201)

  // P6 不连源库、也没有打标数据：取不到时要说清楚怎么办，而不是笼统报错。
  await page.getByRole('button', { name: '从数据库取' }).click()
  const dialog = page.getByRole('dialog', { name: '从数据库取测试数据' })
  await expect(dialog).toContainText('取这一天采集的源政策')
  await expect(dialog).toContainText('@【政策正文】')
  await dialog.getByText('政策解读', { exact: true }).click()
  await dialog.getByRole('button', { name: '取数据' }).click()
  await expect(page.getByText('还没有被判为「需要解读」的政策')).toBeVisible()
  await dialog.getByText('政策类型判断', { exact: true }).click()
  await dialog.getByRole('button', { name: '取数据' }).click()
  await expect(page.getByText('源库暂时连不上，取不了测试数据')).toBeVisible()
  await dialog.getByRole('button', { name: '取消' }).click()

  await page.getByRole('button', { name: '删除模板' }).click()
  await page.getByRole('dialog').getByRole('button', { name: '删除' }).click()
  await expect(page.getByRole('list', { name: '提示词模板' }).getByText(title)).toHaveCount(0)
})
