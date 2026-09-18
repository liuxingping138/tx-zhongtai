import { expect, test, type Route } from '@playwright/test'

const resources = ['policy.sources', 'policy.base_tags', 'policy.interpretations', 'codebook.policy_types', 'codebook.scenarios', 'codebook.area_codes', 'system.users', 'system.roles', 'system.permissions', 'system.audit']
const respond = (route: Route, data: unknown) => route.fulfill({ json: { code: 'OK', data } })

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/csrf')) return respond(route, { csrf_token: 'test' })
    if (path.endsWith('/auth/refresh')) return respond(route, { access_token: 'test', expires_in: 3600, must_change_password: false })
    if (path.endsWith('/auth/me')) return respond(route, { id: 'admin', username: 'admin', display_name: '测试管理员', status: 'active' })
    if (path.endsWith('/auth/permissions')) return respond(route, { resources: resources.map(code => ({ code, level: 'FULL' })), menus: [{ id: 'sources', parent_id: null, title: '信源管理', route_name: 'policy-sources', resource_code: 'policy.sources', sort_order: 1 }] })
    if (path.endsWith('/options')) return respond(route, {})
    return respond(route, { items: [], total: 0, page: 1, page_size: 20 })
  })
})

for (const [path, count] of [
  ['policy/sources', 12], ['policy/base-tags', 16], ['policy/interpretations', 20],
  ['codebook/policy-types', 3], ['codebook/scenarios', 31], ['codebook/area-codes', 11],
] as const) {
  test(`${path}: all database business fields remain editable in grouped forms`, async ({ page }) => {
    await page.goto(`/${path}`)
    await page.getByRole('button', { name: '新增', exact: true }).click()
    await expect(page.locator('.editor-overlay [data-field]')).toHaveCount(count)
    await expect(page.locator('.editor-overlay fieldset').first()).toBeVisible()
    await page.getByRole('button', { name: '取消', exact: true }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
  })
}

test('unsaved form: cancel, Escape and navigation preserve input until discard is confirmed', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('menuitem', { name: '信源管理', exact: true }).click()
  await page.getByRole('button', { name: '新增', exact: true }).click()
  await page.getByRole('dialog').getByLabel('网站名称', { exact: true }).fill('未保存的网站')
  await expect(page.getByText('有未保存的修改')).toBeVisible()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await page.getByRole('button', { name: '继续编辑', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '放弃未保存的修改？', exact: true })).toHaveCount(0)
  await expect(page.getByRole('dialog').getByLabel('网站名称', { exact: true })).toHaveValue('未保存的网站')
  await page.getByRole('dialog').getByLabel('网站名称', { exact: true }).press('Escape')
  await page.getByRole('button', { name: '放弃修改', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button', { name: '新增', exact: true }).click()
  await expect(page.getByRole('dialog').getByLabel('网站名称', { exact: true })).toHaveValue('')
  await page.getByRole('dialog').getByLabel('网站名称', { exact: true }).fill('保留内容')
  // Browser Back is a real route change even while the editor overlay is open.
  await page.goBack()
  await page.getByRole('button', { name: '继续编辑', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '放弃未保存的修改？', exact: true })).toHaveCount(0)
  await expect(page.getByRole('dialog').getByLabel('网站名称', { exact: true })).toHaveValue('保留内容')
})

test('source creation sends visible region codes and closes without a discard prompt after save', async ({ page }) => {
  let payload: Record<string, string> | undefined
  await page.route('**/api/v1/policy/sources', route => {
    payload = route.request().postDataJSON()
    return respond(route, { id: 'new' })
  })
  await page.goto('/policy/sources')
  await page.getByRole('button', { name: '新增', exact: true }).click()
  await page.getByRole('dialog').getByLabel('网站名称', { exact: true }).fill('测试信源')
  await page.getByLabel('区县编码', { exact: true }).fill('110101')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(payload?.district_code).toBe('110101')
  expect(payload?.site_name).toBe('测试信源')
})

test('failed loading exposes retry and filtered empty results can clear filters', async ({ page }) => {
  let fail = true
  await page.route('**/api/v1/codebook/policy-types?**', route => fail
    ? route.fulfill({ status: 500, json: { message: '连接暂时中断' } })
    : respond(route, { items: [], total: 0 }))
  await page.goto('/codebook/policy-types')
  await expect(page.getByRole('alert')).toContainText('连接暂时中断')
  fail = false
  await page.getByRole('button', { name: '重新加载' }).click()
  await expect(page.getByText('暂无记录', { exact: true })).toBeVisible()
  await page.getByRole('combobox', { name: '关键字', exact: true }).fill('不存在的类型')
  await page.getByRole('option', { name: '不存在的类型', exact: true }).click()
  await page.getByRole('button', { name: '查询', exact: true }).click()
  await expect(page.getByText('没有匹配的结果', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '清除筛选', exact: true }).click()
  await expect(page.getByText('暂无记录', { exact: true })).toBeVisible()
})

test('import results persist and include updated counts alongside skipped rows', async ({ page }) => {
  await page.route('**/api/v1/codebook/policy-types/import', route => respond(route, { inserted: 2, updated: 3, skipped: 1, total: 6 }))
  await page.goto('/codebook/policy-types')
  await page.locator('input[type=file]').setInputFiles({ name: 'test.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('mocked workbook') })
  const dialog = page.getByRole('dialog', { name: '导入完成', exact: true })
  await expect(dialog).toBeVisible()
  await expect(dialog.locator('dl')).toContainText('总记录6新增2更新3跳过1')
  await expect(dialog.getByText('test.xlsx', { exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: '完成', exact: true }).click()
  await expect(dialog).toHaveCount(0)
})

test('editing interpretation preserves generated policy UID and tenant identifier', async ({ page }) => {
  let payload: Record<string, unknown> | undefined
  await page.route('**/api/v1/policy/interpretations?**', route => respond(route, { items: [{ id: 'one', policy_title: '已有政策', policy_uid: 'custom-policy-uid', tenant_id: 'tenant-a', version: 2 }], total: 1 }))
  await page.route('**/api/v1/policy/interpretations/one', route => {
    payload = route.request().postDataJSON()
    return respond(route, { id: 'one' })
  })
  await page.goto('/policy/interpretations')
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  await expect(page.getByLabel('租户标识', { exact: true })).toHaveValue('tenant-a')
  await page.getByRole('dialog').getByLabel('政策原文名称', { exact: true }).fill('修改后的政策')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(payload?.policy_uid).toBe('custom-policy-uid')
  expect(payload?.tenant_id).toBe('tenant-a')
})
