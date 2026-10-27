import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

import { currentAdminPassword, loginAdmin } from './adminSession'

test.use({ viewport: { width: 1440, height: 900 } })

// P6 的模型调用全部改发到 llm-mock（deploy/compose/p6/llm_mock.py），不花钱：
// 提示词里有「返回字段：…」就按字段回 JSON；某行内容带「模拟调用失败」时第一次回 400、重跑时成功。
const sampleBook = path.join(import.meta.dirname, 'fixtures', 'ai-template.xlsx')
const batchBook = path.join(import.meta.dirname, 'fixtures', 'ai-batch.xlsx')

/** Element Plus 的下拉：输入框被选中项那层盖住，要点外层包裹元素才能展开。 */
async function choose(page: Page, wrapper: ReturnType<Page['locator']>, option: string | RegExp): Promise<void> {
  await wrapper.locator('.el-select__wrapper').first().click()
  await page.getByRole('option', { name: option }).first().click()
}

test('AI提问主流程：写模板 → 试发 → 样本试跑 → 上线 → 批量任务 → 看结果 → 重跑失败', async ({ page }) => {
  test.skip(!currentAdminPassword(), '缺少 ADMIN_PASSWORD')
  test.setTimeout(180_000)
  const title = `e2e 模板 ${Date.now()}`
  await loginAdmin(page, '/ai/prompts')
  await expect(page.getByRole('navigation', { name: '一级模块' }).getByText('AI提问')).toBeVisible({ timeout: 20_000 })

  // 1. 写提示词：列表 → 新建 → 名称、提示词、输出字段、模型，保存后地址换成模板 ID。
  await page.getByRole('button', { name: '新建模板' }).click()
  await expect(page).toHaveURL(/\/ai\/prompts\/new/)
  const flow = page.getByRole('list', { name: '模板进度' })
  await expect(flow.getByRole('listitem').filter({ hasText: '写提示词' })).toHaveAttribute('aria-current', 'step')
  await page.getByRole('textbox', { name: '模板名称' }).fill(title)
  const content = page.getByRole('textbox', { name: '提示词内容' })
  // 提示词带上本次的标题：模拟模型按提示词记「已经失败过一次」，同一个 P6 里重跑也能再触发失败。
  await content.fill(`${title} 企业：`)
  // 输出字段是标签输入：竖线断开成两个字段，回车收下最后一个。
  const fields = page.getByRole('textbox', { name: '输出字段' })
  await fields.fill('行业|规模')
  await fields.press('Enter')
  await page.getByRole('button', { name: '把格式要求追加到提示词' }).click()
  await expect(content).toHaveValue(/2、返回字段：行业、规模/)
  await choose(page, page.locator('.config .model-picker'), /DeepSeek/)
  await expect(page.getByText('未保存')).toBeVisible()
  const created = page.waitForResponse(r => r.url().endsWith('/api/v1/ai/prompts') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  expect((await created).status()).toBe(201)
  await expect(page).toHaveURL(/\/ai\/prompts\/[0-9a-f]{32}$/)

  // 测试样本：上传后 @ 能插入它的列名。
  const uploaded = page.waitForResponse(r => r.url().includes('/files/excel') && r.request().method() === 'POST')
  await page.locator('input[type=file][accept=".xlsx"]').setInputFiles(sampleBook)
  expect((await uploaded).status()).toBe(200)
  await expect(page.locator('.prompt-files__name').filter({ hasText: 'ai-template.xlsx' })).toContainText('2 行数据')
  await content.click()
  await content.press('ControlOrMeta+Home')
  await content.press('End')
  await content.pressSequentially('@企')
  await page.getByRole('option', { name: '@【企业名称】' }).click()
  await expect(content).toHaveValue(/企业：@【企业名称】/)
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('未保存')).toHaveCount(0)
  await expect(flow.getByRole('listitem').filter({ hasText: '样本试跑' })).toHaveAttribute('aria-current', 'step')

  // 2. 试发一条：模拟模型按输出字段回 JSON。
  await page.getByRole('button', { name: /^试发/ }).click()
  await expect(page.getByRole('log')).toContainText('行业-', { timeout: 20_000 })

  // 样本试跑：从流程条进去，样本 2 行全部跑完，逐行看到解析出的字段。
  await flow.getByRole('button', { name: '去试跑' }).click()
  const sample = page.getByRole('tabpanel', { name: '样本试跑' })
  await sample.getByRole('button', { name: '开始试跑' }).click()
  await expect(sample.getByText('已完成')).toBeVisible({ timeout: 60_000 })
  await expect(sample.getByRole('listitem').filter({ hasText: '第 1 行' })).toContainText('成功')
  await expect(sample.getByRole('listitem').filter({ hasText: '第 2 行' })).toContainText('乙公司')
  await expect(flow.getByRole('listitem').filter({ hasText: '样本试跑' })).toContainText('2 条全部解析成功')
  // 跑完能下载结果 Excel，文件名写明是样本试跑，和正式任务的结果分得开。
  const [sampleFile] = await Promise.all([
    page.waitForEvent('download'),
    sample.getByRole('button', { name: '下载结果' }).click(),
  ])
  expect(sampleFile.suggestedFilename()).toBe(`${title}-样本试跑结果.xlsx`)
  expect(await sampleFile.failure()).toBeNull()

  // 3. 上线：管理员在上线抽屉里看检查项，上线第 1 版。
  await flow.getByRole('button', { name: '上线', exact: true }).click()
  const review = page.getByRole('dialog', { name: `上线「${title}」` })
  await expect(review).toContainText('样本试跑：2 条全部解析成功')
  await review.getByRole('button', { name: '上线第 1 版' }).click()
  await expect(page.getByText('第 1 版已上线').first()).toBeVisible()
  await expect(flow.getByRole('listitem').filter({ hasText: '上线' }).last()).toContainText('第 1 版已上线')

  // 列表里能看到上线状态和试跑结果。
  await page.getByRole('link', { name: '返回模板列表' }).click()
  const row = page.getByRole('row').filter({ hasText: title })
  await expect(row).toContainText('第 1 版已上线')
  await expect(row).toContainText('2 条全部解析成功')

  // 4. 批量任务：选上线的模板，上传这次的数据（3 行，其中一行模拟调用失败），跑全部。
  await page.goto('/ai/batch-runs')
  await page.getByRole('button', { name: '新建批量任务' }).click()
  const drawer = page.getByRole('dialog', { name: '新建批量任务' })
  await choose(page, drawer, new RegExp(title))
  await expect(drawer).toContainText('第 1 版')
  await expect(drawer.locator('.new-task__columns')).toContainText('企业名称')
  // 不知道要哪些列的人先下载数据模板，表头就是上线版本引用的列。
  const [blank] = await Promise.all([
    page.waitForEvent('download'),
    drawer.getByRole('button', { name: '下载数据模板' }).click(),
  ])
  expect(blank.suggestedFilename()).toBe(`${title}-第1版数据模板.xlsx`)
  expect(await blank.failure()).toBeNull()
  const checked = page.waitForResponse(r => r.url().includes('/input-preview') && r.request().method() === 'POST')
  await drawer.locator('input[type=file]').setInputFiles(batchBook)
  expect((await checked).status()).toBe(200)
  await expect(drawer).toContainText('3 行数据')
  await drawer.getByRole('button', { name: /^开始运行/ }).click()
  await page.getByRole('dialog', { name: '开始运行？' }).getByRole('button', { name: '开始运行' }).click()
  const task = page.getByRole('row').filter({ hasText: title }).first()
  await expect(task).toContainText('已完成', { timeout: 60_000 })
  await expect(task).toContainText('3/3，失败 1')
  await expect(task).toContainText('第 1 版')
  await expect(task).toContainText('ai-batch.xlsx')

  // 5. 详情：逐行结果里看到失败原因，重跑失败的那一条后全部成功。
  await task.getByRole('button', { name: '详情' }).click()
  const detail = page.getByRole('dialog', { name: title })
  await expect(detail.getByRole('listitem').filter({ hasText: '第 2 行' })).toContainText('模拟的参数错误')
  await detail.getByRole('button', { name: /^重跑失败的 1 条/ }).click()
  await page.getByRole('dialog', { name: '重跑失败的行？' }).getByRole('button', { name: '开始重跑' }).click()
  await expect(task).toContainText('3/3', { timeout: 60_000 })
  await expect(task).not.toContainText('失败 1', { timeout: 60_000 })
  await expect(detail.getByRole('listitem').filter({ hasText: '第 2 行' })).toContainText('成功', { timeout: 20_000 })
  await detail.getByRole('button', { name: '关闭此对话框' }).click()

  // 费用账单里分得出批量任务和样本试跑。
  await page.goto('/ai/billing')
  await expect(page.getByText('样本试跑').first()).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText('批量任务').first()).toBeVisible()

  // 清理：先下线再删模板。
  await page.goto('/ai/prompts')
  await page.getByRole('link', { name: title }).click()
  await flow.getByRole('button', { name: '上线管理' }).click()
  const online = page.getByRole('dialog', { name: `「${title}」线上版本` })
  await expect(online).toContainText('没有要上线的改动')
  await expect(online.getByRole('button', { name: /^上线第/ })).toHaveCount(0)
  await online.getByRole('button', { name: '下线' }).click()
  await page.getByRole('dialog', { name: '下线模板？' }).getByRole('button', { name: '下线' }).click()
  await expect(flow).toContainText('未上线')
  await page.getByRole('button', { name: '删除模板' }).click()
  await page.getByRole('dialog', { name: '删除模板？' }).getByRole('button', { name: '删除' }).click()
  await expect(page).toHaveURL(/\/ai\/prompts$/)
  await expect(page.getByRole('link', { name: title })).toHaveCount(0)
})

test('批量任务只能选上线的模板；多轮对话能问能答', async ({ page }) => {
  test.skip(!currentAdminPassword(), '缺少 ADMIN_PASSWORD')
  const title = `e2e 草稿 ${Date.now()}`
  await loginAdmin(page, '/ai/prompts/new')
  await page.getByRole('textbox', { name: '模板名称' }).fill(title)
  await page.getByRole('textbox', { name: '提示词内容' }).fill('只是草稿')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page).toHaveURL(/\/ai\/prompts\/[0-9a-f]{32}$/)

  await page.goto('/ai/batch-runs')
  await page.getByRole('button', { name: '新建批量任务' }).click()
  const drawer = page.getByRole('dialog', { name: '新建批量任务' })
  await drawer.locator('.el-select__wrapper').first().click()
  const option = page.getByRole('option', { name: new RegExp(title) })
  await expect(option).toContainText('未上线')
  await expect(option).toHaveClass(/is-disabled/)
  await page.keyboard.press('Escape')
  await expect(drawer.getByRole('button', { name: /^开始运行/ })).toBeDisabled()

  await page.goto('/ai/chat')
  await page.getByRole('textbox', { name: '输入问题' }).fill('你好')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByRole('log')).toContainText('模拟回答', { timeout: 20_000 })
  // 对话不保存：清空前先确认，取消就什么都不动。
  await page.getByRole('button', { name: '新对话' }).click()
  const confirm = page.getByRole('dialog', { name: '开始新对话？' })
  await confirm.getByRole('button', { name: '取消' }).click()
  await expect(page.getByRole('log')).toContainText('模拟回答')
  await page.getByRole('button', { name: '新对话' }).click()
  await confirm.getByRole('button', { name: '清空并开始' }).click()
  await expect(page.getByRole('log')).not.toContainText('模拟回答')
})

test('政策类模板：按草稿提示能不能用于三个打标任务，从数据库取测试数据说清楚取不到的原因', async ({ page }) => {
  test.skip(!currentAdminPassword(), '缺少 ADMIN_PASSWORD')
  const title = `e2e 政策模板 ${Date.now()}`
  await loginAdmin(page, '/ai/prompts')
  await expect(page.getByRole('navigation', { name: '一级模块' }).getByText('AI提问')).toBeVisible({ timeout: 20_000 })
  await page.getByRole('button', { name: '新建模板' }).click()
  await page.getByRole('textbox', { name: '模板名称' }).fill(title)
  await choose(page, page.locator('.config__item').filter({ hasText: '类型' }), '政策类')
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
  await page.getByRole('dialog', { name: '删除模板？' }).getByRole('button', { name: '删除' }).click()
  await expect(page).toHaveURL(/\/ai\/prompts$/)
})
