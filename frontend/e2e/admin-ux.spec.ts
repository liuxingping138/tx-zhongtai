import { expect, test, type Route } from '@playwright/test'

const resources = ['ai.models', 'policy.sources', 'policy.base_tags', 'policy.interpretations', 'codebook.policy_types', 'codebook.scenarios', 'codebook.area_codes', 'system.users', 'system.roles', 'system.permissions', 'system.audit']
const respond = (route: Route, data: unknown) => route.fulfill({ json: { code: 'OK', data } })

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/csrf')) return respond(route, { csrf_token: 'test' })
    if (path.endsWith('/auth/refresh')) return respond(route, { access_token: 'test', expires_in: 3600, must_change_password: false })
    if (path.endsWith('/auth/me')) return respond(route, { id: 'admin', username: 'admin', display_name: '测试管理员', status: 'active', roles: ['超级管理员'] })
    if (path.endsWith('/auth/permissions')) return respond(route, { resources: resources.map(code => ({ code, level: 'FULL' })), menus: [{ id: 'sources', parent_id: null, title: '信源管理', route_name: 'policy-sources', resource_code: 'policy.sources', sort_order: 1 }] })
    if (path.endsWith('/options')) return respond(route, {})
    if (path.endsWith('/ai/models')) return respond(route, [])
    return respond(route, { items: [], total: 0, page: 1, page_size: 20 })
  })
})

test('column picker defaults to all fields and can restore the full set', async ({ page }) => {
  await page.goto('/codebook/scenarios')
  const picker = page.getByRole('button', { name: /列设置/ })
  await expect(picker).toContainText('37/37')
  await picker.click()
  await expect(page.getByRole('button', { name: '显示全部列', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '恢复默认列', exact: true })).toBeVisible()
  // Element Plus 的原生 checkbox 被隐藏（opacity:0、0x0），可见的是样式化替身，
  // 直接对原生元素 uncheck() 会一直等它可见。点可见的标签。
  await page.locator('.el-checkbox').filter({ hasText: /^场景标签$/ }).click()
  await expect(picker).toContainText('36/37')
  await page.getByRole('button', { name: '恢复默认列', exact: true }).click()
  await expect(picker).toContainText('37/37')
})

for (const [path, count] of [
  ['policy/sources', 15], ['policy/base-tags', 16], ['policy/interpretations', 24],
  ['codebook/policy-types', 4], ['codebook/scenarios', 31], ['codebook/area-codes', 11], ['ai/models', 19],
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
  await page.route('**/api/v1/auth/permissions', route => respond(route, {
    resources: resources.map(code => ({ code, level: 'FULL' })),
    menus: [
      { id: 'policy', parent_id: null, title: '政策', route_name: null, resource_code: null, sort_order: 1 },
      { id: 'sources', parent_id: 'policy', title: '信源管理', route_name: 'policy-sources', resource_code: 'policy.sources', sort_order: 1 },
      { id: 'codebook', parent_id: null, title: '码表管理', route_name: null, resource_code: null, sort_order: 2 },
      { id: 'types', parent_id: 'codebook', title: '政策类型', route_name: 'codebook-policy-types', resource_code: 'codebook.policy_types', sort_order: 1 },
    ],
  }))
  await page.goto('/codebook/policy-types')
  await page.getByRole('navigation', { name: '一级模块' }).getByRole('link', { name: '政策', exact: true }).click()
  await expect(page).toHaveURL(/\/policy\/sources$/)
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
  await page.locator('.el-drawer').getByLabel('区县编码', { exact: true }).fill('110101')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(payload?.district_code).toBe('110101')
  expect(payload?.site_name).toBe('测试信源')
})

test('desktop shows one row of filters, expands the rest, and distinguishes draft from applied query', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/policy/sources')
  await expect(page.getByRole('combobox', { name: '网站名称', exact: true })).toBeVisible()
  // 一行放不下的条件先收起，点「展开」才出来。
  await expect(page.getByRole('combobox', { name: '网站优先级', exact: true })).toBeHidden()
  await page.getByRole('button', { name: /^展开筛选条件/ }).click()
  await expect(page.getByRole('combobox', { name: '标签', exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: '网站优先级', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '收起筛选条件' })).toBeVisible()
  await expect(page.getByRole('button', { name: '重置', exact: true })).toBeDisabled()
  await page.getByRole('combobox', { name: '网站名称', exact: true }).fill('北京日报')
  await page.getByRole('option', { name: '北京日报', exact: true }).click()
  await expect(page.getByText('条件已改，点击查询后生效', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '查询', exact: true }).click()
  await expect(page.getByText('已筛选 1 项', { exact: true })).toBeVisible()
})

// 适配范围是电脑端 1024px 起（见 DESIGN.md「适配范围」）。
// 1024 是下限，最容易出问题：列多、容器窄，既不能让整页横向溢出，
// 也不能因为窄就退化成移动端摘要卡片，上传下载入口还必须留着。
test('1024px 下限：无整页横溢出、工具栏入口齐全、筛选可展开、横滑到末列仍能操作', async ({ page }) => {
  await page.route('**/api/v1/policy/sources?**', route => respond(route, {
    items: [{ id: 'row-1', site_name: '北京日报', province_name: '北京市', department: '宣传部' }],
    total: 1,
    page: 1,
    page_size: 20,
  }))
  await page.setViewportSize({ width: 1024, height: 768 })
  await page.goto('/policy/sources')

  // 整页不许横向溢出；表格自身超宽是允许的，它在 ScrollPort 里滚。
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow).toBeLessThanOrEqual(0)

  // 导入和导出入口必须保留，且真的落在视口内。
  for (const name of [/^导入$/, /^导出$/, /列设置/]) {
    const button = page.getByRole('button', { name }).first()
    await expect(button).toBeVisible()
    const box = await button.boundingBox()
    expect(box!.x + box!.width).toBeLessThanOrEqual(1024)
  }

  // 放不下的条件收进「展开」，不出现手机的「更多筛选」。
  await expect(page.getByRole('button', { name: /^展开筛选条件/ })).toBeVisible()
  await expect(page.getByRole('button', { name: '更多筛选' })).toHaveCount(0)
  // 也不许退化成移动端摘要卡片。
  await expect(page.locator('.mobile-record')).toHaveCount(0)

  // 横滑到最右，操作列仍要在视口内可点。
  const scrolled = await page.evaluate(() => {
    const port = [...document.querySelectorAll('div')].find(d => d.scrollWidth > d.clientWidth + 1 && d.clientWidth > 300)
    if (!port) return false
    port.scrollLeft = port.scrollWidth
    return true
  })
  expect(scrolled).toBe(true)
  const opHeader = page.getByRole('columnheader', { name: '操作' }).first()
  await expect(opHeader).toBeVisible()
  const opBox = await opHeader.boundingBox()
  expect(opBox!.x + opBox!.width).toBeLessThanOrEqual(1024)
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

test('列表点编辑进核对页就能改，各组一起保存，政策唯一标识和租户标识原样提交', async ({ page }) => {
  let payload: Record<string, unknown> | undefined
  const row = { id: 'one', policy_title: '已有政策', policy_uid: 'custom-policy-uid', tenant_id: 'tenant-a', data_status: '待验证', version: 2 }
  await page.route('**/api/v1/policy/interpretations?**', route => respond(route, { items: [row], total: 1 }))
  await page.route('**/api/v1/policy/interpretations/one', route => {
    if (route.request().method() !== 'PATCH') return respond(route, row)
    payload = route.request().postDataJSON()
    return respond(route, { ...row, ...payload, version: 3 })
  })
  await page.route('**/api/v1/policy/interpretations/one/content', route =>
    route.fulfill({ status: 404, json: { code: 'RESOURCE_NOT_FOUND', message: '这条不是从源库打标的，没有正文' } }))
  await page.goto('/policy/interpretations')
  await page.getByRole('row').filter({ hasText: '已有政策' }).getByRole('link', { name: '编辑', exact: true }).click()
  // 打开就是编辑状态：所有分组一起变成输入框，只有底部一个保存。
  const basic = page.getByRole('region', { name: '基本信息' })
  await expect(basic.getByLabel('租户标识', { exact: true })).toHaveValue('tenant-a')
  await expect(page.getByRole('region', { name: '解读内容' }).getByRole('textbox').first()).toBeEditable()
  await expect(page.getByRole('button', { name: '编辑', exact: true })).toHaveCount(0)
  await expect(page).not.toHaveURL(/edit=1/)
  await basic.getByLabel('政策原文名称', { exact: true }).fill('修改后的政策')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('已保存')).toBeVisible()
  expect(payload?.policy_uid).toBe('custom-policy-uid')
  expect(payload?.tenant_id).toBe('tenant-a')
  expect(payload?.version).toBe(2)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('修改后的政策')
  await expect(page.getByRole('button', { name: '编辑', exact: true })).toBeVisible()
})

test('基础标签：按打标状态筛出来，勾选后重新打标，跳过的逐条说明原因', async ({ page }) => {
  let payload: Record<string, unknown> | undefined
  await page.route('**/api/v1/policy/base-tags?**', route => respond(route, {
    items: [
      { id: 't1', policy_name: '解读失败的政策', remark: 'AI 解读失败：限流', need_interpret: '是', ai_status: '解读失败', version: 1 },
      { id: 't2', policy_name: '手工录入的政策', remark: '', need_interpret: '是', ai_status: '', version: 1 },
    ],
    total: 2,
  }))
  await page.route('**/api/v1/policy/ai-tagging/retag', route => {
    payload = route.request().postDataJSON()
    return respond(route, { step: 'interpret', task: '政策解读', queued: 1, skipped: [{ reason: '手工录入或导入的政策没有源政策，不能重新打标', count: 1 }] })
  })
  // 1280 宽一行放不下六个条件，排在第六个的打标状态收在「展开」里。
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/policy/base-tags')
  await page.getByRole('button', { name: /^展开筛选条件/ }).click()
  await expect(page.locator('.el-form-item').filter({ hasText: '打标状态' })).toBeVisible()
  // 表里也有一列打标状态：哪条卡在哪一步，不用先筛选才知道。
  await expect(page.getByRole('row').filter({ hasText: '解读失败的政策' })).toContainText('解读失败')
  const retag = page.getByRole('button', { name: /^重新打标/ })
  await expect(retag).toBeDisabled()
  // 表头的全选框：样式化的可见替身，点它。
  await page.locator('.el-table__header .el-checkbox').click()
  await expect(retag).toHaveText('重新打标（2）')
  await retag.click()
  const dialog = page.getByRole('dialog', { name: '重新打标' })
  await dialog.getByText('重新解读', { exact: true }).click()
  await expect(dialog).toContainText('人工验证过的解读行保留')
  await dialog.getByRole('button', { name: '确定' }).click()
  const alert = page.locator('.el-message-box')
  await expect(alert).toContainText('已把 1 条放回「政策解读」的待办')
  await expect(alert).toContainText('1 条：手工录入或导入的政策没有源政策，不能重新打标')
  expect(payload).toEqual({ ids: ['t1', 't2'], step: 'interpret' })
})

test('政策解读：勾选多条一次改成人工验证', async ({ page }) => {
  let payload: Record<string, unknown> | undefined
  await page.route('**/api/v1/policy/interpretations?**', route => respond(route, {
    items: [
      { id: 'i1', policy_title: '政策一', data_status: '待验证', version: 1 },
      { id: 'i2', policy_title: '政策二', data_status: '待验证', version: 1 },
    ],
    total: 2,
  }))
  await page.route('**/api/v1/policy/interpretations/data-status', route => {
    payload = route.request().postDataJSON()
    return respond(route, { updated: 2, unchanged: 0 })
  })
  await page.goto('/policy/interpretations')
  await page.locator('.el-table__header .el-checkbox').click()
  await page.getByRole('button', { name: '批量改数据状态（2）' }).click()
  const dialog = page.getByRole('dialog', { name: '批量改数据状态' })
  await expect(dialog).toContainText('之后 AI 重新解读、回填市场机会都不会再覆盖这些行')
  await dialog.getByRole('button', { name: '确定' }).click()
  await expect(page.getByText('已改 2 条')).toBeVisible()
  expect(payload).toEqual({ ids: ['i1', 'i2'], data_status: '人工验证' })
})

test('政策解读核对页：读完标为人工验证，接着打开下一条', async ({ page }) => {
  let payload: Record<string, unknown> | undefined
  const rows = [
    { id: 'i1', policy_title: '待核对的政策', data_status: '待验证', version: 1 },
    { id: 'i2', policy_title: '核对过的政策', data_status: '人工验证', version: 1 },
  ]
  await page.route('**/api/v1/policy/interpretations?**', (route) => {
    const params = new URL(route.request().url()).searchParams
    const size = Number(params.get('page_size') ?? 20)
    const at = Number(params.get('page') ?? 1)
    return respond(route, { items: rows.slice((at - 1) * size, at * size), total: rows.length, page: at, page_size: size })
  })
  for (const row of rows) await page.route(`**/api/v1/policy/interpretations/${row.id}`, route => respond(route, row))
  await page.route('**/api/v1/policy/interpretations/data-status', route => {
    payload = route.request().postDataJSON()
    return respond(route, { updated: 1, unchanged: 0 })
  })
  // 正文打开核对页才去源库取：手工录入的行说明没有正文。
  await page.route('**/api/v1/policy/interpretations/i2/content', route =>
    route.fulfill({ status: 404, json: { code: 'RESOURCE_NOT_FOUND', message: '这条不是从源库打标的，没有正文' } }))
  await page.route('**/api/v1/policy/interpretations/i1/content', route => respond(route, {
    title: '待核对的政策',
    text: Array.from({ length: 10 }, (_, index) => `第 ${index + 1} 段正文`).join('\n'),
    source_url: 'https://example.gov.cn/p/1',
    issued_at: '2026-10-01',
    chars: 60,
  }))
  await page.goto('/policy/interpretations')
  await page.getByRole('link', { name: '待核对的政策' }).click()
  await expect(page).toHaveURL(/\/policy\/interpretations\/i1\?pos=0$/)
  await expect(page.getByText('第 1 条，共 2 条（当前筛选）')).toBeVisible()
  // 正文在右栏直接给全文，不用再点展开。
  const content = page.getByRole('region', { name: '政策正文' })
  await expect(content).toContainText('第 10 段正文')
  await expect(content.getByRole('link', { name: '打开原网页' })).toHaveAttribute('href', 'https://example.gov.cn/p/1')
  await page.getByRole('button', { name: '核对无误，标为人工验证' }).click()
  await expect(page.getByText('已标为人工验证，打开了下一条')).toBeVisible()
  expect(payload).toEqual({ ids: ['i1'], data_status: '人工验证' })
  await expect(page).toHaveURL(/\/policy\/interpretations\/i2\?pos=1$/)
  // 已经人工验证的不再给这个按钮；最后一条没有下一条。
  await expect(page.getByRole('button', { name: '核对无误，标为人工验证' })).toHaveCount(0)
  await expect(page.getByText('这条不是从源库打标的，没有正文')).toBeVisible()
  await expect(page.getByRole('button', { name: '下一条' })).toBeDisabled()
  await page.getByRole('button', { name: '返回政策解读列表' }).click()
  await expect(page).toHaveURL(/\/policy\/interpretations$/)
})

test('信源管理：列表显示网站编码和内部唯一id', async ({ page }) => {
  await page.route('**/api/v1/policy/sources?**', route => respond(route, {
    items: [{ id: 's1', site_name: '某市人民政府', site_code: '11010100001', internal_id: 'abc123', version: 1 }],
    total: 1,
  }))
  await page.goto('/policy/sources')
  const header = page.locator('.el-table__header')
  await expect(header).toContainText('网站编码')
  await expect(header).toContainText('内部唯一id')
  await expect(page.locator('.el-table__body')).toContainText('11010100001')
})
