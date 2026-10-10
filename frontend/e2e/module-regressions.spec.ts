import { expect, test, type Page, type Route } from '@playwright/test'

const resources = ['policy.sources', 'policy.base_tags', 'policy.interpretations', 'codebook.policy_types', 'codebook.scenarios', 'codebook.area_codes', 'system.users', 'system.roles', 'system.permissions', 'system.audit']
const role = (id: string) => ({ id, name: `角色${id}`, code: `role_${id}`, status: 'active', version: 1, is_builtin: false })
const respond = (route: Route, data: unknown) => route.fulfill({ json: { code: 'OK', data } })

async function mockSession(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/csrf')) return respond(route, { csrf_token: 'test' })
    if (path.endsWith('/auth/refresh')) return respond(route, { access_token: 'test', expires_in: 3600, must_change_password: false })
    if (path.endsWith('/auth/me')) return respond(route, { id: 'admin', username: 'admin', display_name: '测试管理员', status: 'active', roles: ['超级管理员'] })
    if (path.endsWith('/auth/permissions')) return respond(route, { resources: resources.map(code => ({ code, level: 'FULL' })), menus: [] })
    if (path.endsWith('/options')) return respond(route, {})
    return respond(route, { items: [], total: 0, page: 1, page_size: 20 })
  })
}

test.beforeEach(async ({ page }) => { await mockSession(page) })

for (const module of ['policy/sources', 'codebook/policy-types', 'system/users']) {
  test(`${module}: late response does not overwrite a newer query`, async ({ page }) => {
    let first: Route | undefined
    let calls = 0
    await page.route(`**/api/v1/${module}?**`, async route => {
      const url = new URL(route.request().url())
      // 下拉选项（100 条）和「待分配角色」计数（1 条）不是列表查询，直接放过。
      if (['100', '1'].includes(url.searchParams.get('page_size') ?? '')) return respond(route, { items: [], total: 0 })
      calls += 1
      if (calls === 1) { first = route; return }
      return respond(route, { items: [{ id: 'new', site_name: '最新结果', type_name: '最新结果', username: '最新结果' }], total: 1 })
    })
    await page.goto(`/${module}`)
    await expect.poll(() => first !== undefined).toBe(true)
    await page.getByRole('button', { name: '查询', exact: true }).click()
    await expect(page.getByText('最新结果', { exact: true })).toBeVisible()
    await respond(first!, { items: [{ id: 'old', site_name: '过期结果', type_name: '过期结果', username: '过期结果' }], total: 1 })
    await expect(page.getByText('最新结果', { exact: true })).toBeVisible()
    await expect(page.getByText('过期结果', { exact: true })).toHaveCount(0)
  })
}

test('audit: clearing the date range still submits the query', async ({ page }) => {
  await page.goto('/system/audit')
  const inputs = page.locator('.el-range-input')
  await inputs.nth(0).fill('2026-09-01 00:00:00')
  await inputs.nth(1).fill('2026-09-18 23:59:59')
  await inputs.nth(1).press('Enter')
  // 列表标题只给读屏用，并且被筛选区盖住，点它关不掉日期面板。点工具栏。
  await page.locator('.list-page__toolbar').click()
  await page.locator('.el-date-editor').hover()
  // 清除图标只在 hover 时出现且带过渡动画，click() 等不到 stable；
  // force 点击又会因为指针移开而丢掉 hover，真正生效的是直接派发 click 事件。
  await page.locator('.el-range__close-icon').dispatchEvent('click')
  const request = page.waitForRequest(r => r.url().includes('/audit/events?'))
  await page.getByRole('button', { name: '查询', exact: true }).click()
  const url = new URL((await request).url())
  expect(url.searchParams.has('occurred_from')).toBe(false)
  expect(url.searchParams.has('occurred_to')).toBe(false)
})

const sourcesTree = [{
  id: 'g', code: 'policy', name: '政策', node_type: 'directory', published: true, children: [
    { id: 'r', code: 'policy.sources', name: '信源管理', node_type: 'resource', published: true, children: [],
      actions: [{ action_code: 'list', required_level: 'READ' }, { action_code: 'export', required_level: 'EXPORT' }, { action_code: 'create', required_level: 'FULL' }] },
    { id: 'c', code: 'policy.crawler_monitoring_v2', name: '爬虫监测', node_type: 'resource', published: true, children: [],
      actions: [{ action_code: 'list', required_level: 'READ' }, { action_code: 'export', required_level: 'EXPORT' }] },
  ],
}, { id: 'u', code: 'customer', name: '客户', node_type: 'directory', published: false, children: [] }]

/** 角色详情页需要的三个接口：角色本身、资源树、授权。 */
async function mockRoleDetail(page: Page, grants: (id: string, route: Route) => Promise<void> | void) {
  await page.route('**/api/v1/system/roles/*', route => {
    const id = new URL(route.request().url()).pathname.split('/').pop() ?? '1'
    return respond(route, { ...role(id), member_count: 0, grant_counts: { read: 0, export: 0, full: 0 } })
  })
  await page.route('**/api/v1/system/resources', route => respond(route, { tree: sourcesTree }))
  await page.route('**/api/v1/system/roles/*/grants', route => {
    const id = new URL(route.request().url()).pathname.split('/').slice(-2)[0]
    return grants(id, route)
  })
}

test('roles: old permission links open the role detail page', async ({ page }) => {
  await mockRoleDetail(page, (id, route) => respond(route, { role: role(id), grants: [] }))
  await page.goto('/system/roles/2/grants')
  await expect(page).toHaveURL(/\/system\/roles\/2$/)
  await expect(page.getByRole('heading', { name: '角色2' })).toBeVisible()
  await page.goto('/system/permissions?roleId=1')
  await expect(page).toHaveURL(/\/system\/roles\/1$/)
  await expect(page.getByRole('heading', { name: '角色1' })).toBeVisible()
  await page.goto('/system/permissions')
  await expect(page).toHaveURL(/\/system\/roles$/)
})

test('roles: left list selects the first role, switches the right side, and guards unsaved grants', async ({ page }) => {
  const items = [{ ...role('1'), name: '政策数据管理员', description: '负责政策表', member_count: 3 },
    { ...role('2'), name: '码表管理员', member_count: 0 }]
  await page.route('**/api/v1/system/roles?**', route => respond(route, { items, total: items.length }))
  await page.route('**/api/v1/system/roles/*', route => {
    const id = new URL(route.request().url()).pathname.split('/').pop() ?? '1'
    const item = items.find(entry => entry.id === id) ?? items[0]
    return respond(route, { ...item, grant_counts: { read: 0, export: 0, full: 0 } })
  })
  await page.route('**/api/v1/system/resources', route => respond(route, { tree: sourcesTree }))
  await page.route('**/api/v1/system/roles/*/grants', route => respond(route, { role: role('1'), grants: [] }))
  await page.route('**/api/v1/auth/permissions', route => respond(route, {
    resources: resources.map(code => ({ code, level: 'FULL' })),
    menus: [
      { id: 'm-sys', parent_id: null, title: '系统管理', route_name: null, resource_code: null, icon: 'setting', sort_order: 10 },
      { id: 'm-roles', parent_id: 'm-sys', title: '角色与权限', route_name: 'system-roles', resource_code: 'system.roles', icon: null, sort_order: 12 },
    ],
  }))
  await page.goto('/system/roles')
  // 没指定角色时默认打开第一个，右边不留空白。
  await expect(page).toHaveURL(/\/system\/roles\/1$/)
  const nav = page.getByRole('complementary', { name: '角色列表' })
  await expect(nav.getByRole('button', { name: /政策数据管理员/ })).toHaveAttribute('aria-current', 'true')
  await expect(nav.getByRole('button', { name: /政策数据管理员/ })).toContainText('3 人')
  await expect(nav.getByRole('button', { name: /政策数据管理员/ })).toContainText('负责政策表')
  await expect(page.getByRole('heading', { name: '政策数据管理员', exact: true })).toBeVisible()

  // 有未保存的权限修改时切换角色先确认；选「继续编辑」留在原角色。
  await page.getByRole('checkbox', { name: '信源管理 查看', exact: true }).check()
  await nav.getByRole('button', { name: /码表管理员/ }).click()
  const discard = page.locator('.el-message-box')
  await expect(discard).toContainText('切换后将丢弃')
  await discard.getByRole('button', { name: '继续编辑' }).click()
  await expect(discard).toHaveCount(0)
  await expect(page).toHaveURL(/\/system\/roles\/1$/)

  await page.getByRole('button', { name: '放弃修改', exact: true }).click()
  await nav.getByRole('button', { name: /码表管理员/ }).click()
  await expect(page).toHaveURL(/\/system\/roles\/2$/)
  await expect(page.getByRole('heading', { name: '码表管理员', exact: true })).toBeVisible()
  await expect(nav.getByRole('button', { name: /码表管理员/ })).toHaveAttribute('aria-current', 'true')
  // 侧栏仍高亮「角色与权限」。
  await expect(page.getByRole('navigation', { name: '子模块导航' }).getByRole('link', { name: '角色与权限', exact: true })).toHaveAttribute('aria-current', 'page')
})

test('roles: permission matrix cascades columns; saving locks the row and confirms in plain Chinese', async ({ page }) => {
  let saving: Route | undefined
  let payload: { grants: { resource_code: string; level: string }[] } | undefined
  await mockRoleDetail(page, (id, route) => {
    if (route.request().method() === 'PUT') { saving = route; payload = route.request().postDataJSON(); return }
    return respond(route, { role: role(id), grants: [] })
  })
  await page.goto('/system/roles/1')
  const sources = page.locator('.perm-table__row').filter({ hasText: '信源管理' })
  const cell = (name: string) => sources.getByRole('checkbox', { name: `信源管理 ${name}`, exact: true })
  // 勾「管理」自动带上查看和导出，保存档位是 FULL。
  await cell('管理').check()
  await expect(cell('查看')).toBeChecked()
  await expect(cell('导出')).toBeChecked()
  await expect(page.getByText('有 1 项修改还没保存')).toBeVisible()
  // 取消「查看」整行清空，等于没改。
  await cell('查看').uncheck()
  await expect(cell('管理')).not.toBeChecked()
  await expect(page.getByText('有 1 项修改还没保存')).toHaveCount(0)
  await cell('导出').check()
  await expect(cell('查看')).toBeChecked()
  await expect(cell('管理')).not.toBeChecked()

  await page.getByRole('button', { name: '保存权限', exact: true }).click()
  const confirm = page.locator('.el-message-box')
  await expect(confirm).toContainText('政策 / 信源管理：无权限 → 查看和导出')
  await confirm.getByRole('button', { name: '保存', exact: true }).click()
  await expect.poll(() => saving !== undefined).toBe(true)
  expect(payload?.grants.find(item => item.resource_code === 'policy.sources')?.level).toBe('EXPORT')
  await expect(cell('导出')).toBeDisabled()
  await respond(saving!, { role: { ...role('1'), version: 2 }, grants: [{ resource_code: 'policy.sources', level: 'EXPORT' }] })
  await expect(page.getByText('有 1 项修改还没保存')).toHaveCount(0)
})

test('roles: modules only show the columns they actually have; unreleased modules are hidden', async ({ page }) => {
  await mockRoleDetail(page, (id, route) => respond(route, { role: role(id), grants: [] }))
  await page.goto('/system/roles/1')
  const crawler = page.locator('.perm-table__row').filter({ hasText: '爬虫监测' })
  await expect(crawler.getByRole('checkbox')).toHaveCount(2)
  await expect(crawler.getByRole('checkbox', { name: '爬虫监测 管理', exact: true })).toHaveCount(0)
  await expect(crawler).toContainText('只读模块，没有新增或修改操作')
  await expect(page.locator('.perm-table__row').filter({ hasText: '信源管理' })).toContainText('管理包含：新增')
  await expect(page.getByText('客户', { exact: true })).toHaveCount(0)

  await page.getByLabel('搜索菜单').fill('爬虫')
  await expect(page.getByText('信源管理', { exact: true })).toHaveCount(0)
  await expect(crawler).toBeVisible()
  await page.getByLabel('搜索菜单').fill('')
  await expect(page.getByText('信源管理', { exact: true })).toBeVisible()

  // 整组一列：勾「导出」两个菜单都到导出；再点一次全部取消导出、回到仅查看。
  const groupExport = page.getByRole('checkbox', { name: '政策整组导出', exact: true })
  await groupExport.check()
  await expect(page.getByRole('checkbox', { name: '信源管理 导出', exact: true })).toBeChecked()
  await expect(crawler.getByRole('checkbox', { name: '爬虫监测 导出', exact: true })).toBeChecked()
  await expect(page.getByRole('checkbox', { name: '政策整组查看', exact: true })).toBeChecked()
  await expect(page.getByText('有 2 项修改还没保存')).toBeVisible()
  await groupExport.uncheck()
  await expect(crawler.getByRole('checkbox', { name: '爬虫监测 查看', exact: true })).toBeChecked()
  await page.getByRole('checkbox', { name: '政策整组查看', exact: true }).uncheck()
  await expect(page.getByText('有 2 项修改还没保存')).toHaveCount(0)
})

test('forbidden page keeps the allowed menu and returns to it', async ({ page }) => {
  await page.route('**/api/v1/auth/permissions', route => respond(route, {
    resources: [{ code: 'codebook.area_codes', level: 'FULL' }],
    menus: [
      { id: 'm-code', parent_id: null, title: '码表管理', route_name: null, resource_code: null, icon: null, sort_order: 1 },
      { id: 'm-area', parent_id: 'm-code', title: '省市区编码表', route_name: 'codebook-area-codes', resource_code: 'codebook.area_codes', icon: null, sort_order: 1 },
    ],
  }))
  await page.route('**/api/v1/codebook/area-codes**', route => respond(route, { items: [], total: 0, page: 1, page_size: 20 }))
  await page.goto('/policy/sources')
  await expect(page).toHaveURL(/\/forbidden/)
  await expect(page.getByText('这个页面不在当前角色的菜单里')).toBeVisible()
  const sidebar = page.getByRole('navigation', { name: '子模块导航' })
  await expect(sidebar.getByRole('link', { name: '省市区编码表' })).toBeVisible()
  await page.getByRole('button', { name: '返回省市区编码表' }).click()
  await expect(page).toHaveURL(/\/codebook\/area-codes/)
})

test('roles: detail load failure shows a persistent error with a working retry', async ({ page }) => {
  // 原来初次加载失败只弹一个会消失的 toast，页面空着且没有重试入口，只能刷整页。
  let attempts = 0
  await mockRoleDetail(page, (id, route) => {
    attempts += 1
    if (attempts === 1) return route.fulfill({ status: 503, json: { message: '授权服务暂时不可用' } })
    return respond(route, { role: role(id), grants: [] })
  })
  await page.goto('/system/roles/1')
  const error = page.getByRole('alert').filter({ hasText: '暂时无法加载这个角色' })
  await expect(error).toBeVisible()
  await expect(error).toContainText('授权服务暂时不可用')
  await error.getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.getByRole('heading', { name: '角色1' })).toBeVisible()
})

test('roles: members can be added and removed from the role side', async ({ page }) => {
  const members: { id: string; username: string; display_name: string; status: string }[] = []
  await mockRoleDetail(page, (id, route) => respond(route, { role: role(id), grants: [] }))
  await page.route('**/api/v1/system/users?**', route => respond(route, {
    items: [{ id: 'u1', username: 'zhangsan', display_name: '张三', status: 'active', version: 1 }], total: 1,
  }))
  let added: unknown
  await page.route('**/api/v1/system/roles/1/members**', async route => {
    const method = route.request().method()
    if (method === 'POST') {
      added = route.request().postDataJSON()
      members.push({ id: 'u1', username: 'zhangsan', display_name: '张三', status: 'active' })
      return respond(route, { added: 1, items: members })
    }
    if (method === 'DELETE') { members.length = 0; return respond(route, { items: members }) }
    return respond(route, { items: members })
  })
  await page.goto('/system/roles/1?tab=members')
  await expect(page.getByText('还没有成员')).toBeVisible()
  await page.getByRole('button', { name: '添加成员' }).click()
  const dialog = page.getByRole('dialog', { name: '添加成员' })
  await dialog.locator('.el-select__wrapper').click()
  await page.getByRole('option', { name: /张三/ }).click()
  // 选中后下拉自动收起，不会盖住底部按钮。
  await expect(page.getByRole('option', { name: /张三/ })).toBeHidden()
  await dialog.getByRole('button', { name: /添加 1 人/ }).click()
  expect(added).toEqual({ user_ids: ['u1'] })
  await expect(page.locator('.members__table')).toContainText('zhangsan')
  await expect(page.getByRole('tab', { name: /成员/ })).toContainText('1')
  await page.getByRole('button', { name: '移出' }).click()
  await page.locator('.el-message-box').getByRole('button', { name: '移出' }).click()
  await expect(page.getByText('还没有成员')).toBeVisible()
})

test('users: create a user with roles in one step, and list shows roles', async ({ page }) => {
  const roles = [{ ...role('1'), name: '政策数据管理员', description: '负责政策表维护', grant_counts: { read: 1, full: 2 } }]
  let created: { role_ids?: string[] } | undefined
  await page.route('**/api/v1/system/roles?**', route => respond(route, { items: roles, total: 1 }))
  await page.route('**/api/v1/system/users**', route => {
    if (route.request().method() === 'POST') {
      created = route.request().postDataJSON()
      return respond(route, { user: { id: 'u9', username: 'lisi', display_name: '李四', status: 'active', version: 1, roles: [] } })
    }
    return respond(route, {
      items: [
        { id: 'u1', username: 'zhangsan', display_name: '张三', status: 'active', version: 1, created_at: '2026-09-23T08:00:00+00:00', roles: [{ id: '1', name: '政策数据管理员', status: 'active', is_builtin: false }] },
        { id: 'u2', username: 'wangwu', display_name: '王五', status: 'active', version: 1, created_at: '2026-09-23T08:00:00+00:00', roles: [] },
      ],
      total: 2,
    })
  })
  await page.goto('/system/users')
  await expect(page.getByRole('row').filter({ hasText: 'zhangsan' })).toContainText('政策数据管理员')
  await expect(page.getByRole('row').filter({ hasText: 'wangwu' })).toContainText('待分配角色')
  // 没有角色的人，操作直接是「分配角色」。
  await expect(page.getByRole('row').filter({ hasText: 'wangwu' }).getByRole('button', { name: '分配角色' })).toBeVisible()

  await page.getByRole('button', { name: '新增用户' }).click()
  const dialog = page.getByRole('dialog', { name: '新增用户' })
  await dialog.getByLabel('用户名', { exact: true }).fill('lisi')
  await dialog.getByLabel('显示名', { exact: true }).fill('李四')
  // 浏览器不能把已保存的管理员账号自动填进来。
  await expect(dialog.getByLabel('用户名', { exact: true })).toHaveAttribute('autocomplete', 'off')
  await expect(dialog.getByLabel('显示名', { exact: true })).toHaveAttribute('autocomplete', 'off')
  // 初始密码只由系统生成，不提供手填。
  await expect(dialog.locator('input[type="password"]')).toHaveCount(0)
  await expect(dialog.getByText('创建后由系统生成，只显示一次')).toBeVisible()

  // 没选角色不预先警告，提交时确认一次；选择「返回选择」不会创建。
  await dialog.getByRole('button', { name: '创建', exact: true }).click()
  const confirm = page.getByRole('dialog', { name: '还没有选择角色' })
  await expect(confirm).toBeVisible()
  await confirm.getByRole('button', { name: '返回选择' }).click()
  expect(created).toBeUndefined()

  await dialog.getByRole('checkbox', { name: /政策数据管理员/ }).click()
  await expect(dialog.getByRole('checkbox', { name: /政策数据管理员/ })).toHaveAttribute('aria-checked', 'true')
  await expect(dialog.getByText('负责政策表维护')).toBeVisible()
  await dialog.getByRole('button', { name: '创建', exact: true }).click()
  await expect.poll(() => created?.role_ids).toEqual(['1'])
  expect(created).not.toHaveProperty('password')
})

test('users: pending-role bar filters to accounts without roles', async ({ page }) => {
  const requests: URL[] = []
  await page.route('**/api/v1/system/roles?**', route => respond(route, { items: [role('1')], total: 1 }))
  await page.route('**/api/v1/system/users?**', route => {
    const url = new URL(route.request().url())
    requests.push(url)
    if (url.searchParams.get('page_size') === '1') return respond(route, { items: [], total: 3 })
    return respond(route, {
      items: [{ id: 'u1', username: 'zhaolei', display_name: '赵磊', phone: '13588123307', email: 'zl@example.com', status: 'active', version: 1, created_at: '2026-09-23T08:00:00+00:00', roles: [] }],
      total: 1,
    })
  })
  await page.goto('/system/users')
  const row = page.getByRole('row').filter({ hasText: 'zhaolei' })
  await expect(row).toContainText('13588123307')
  await expect(row).toContainText('zl@example.com')
  await expect(page.getByText('有 3 个账号还没分配角色')).toBeVisible()
  await page.getByRole('button', { name: '只看这些' }).click()
  await expect.poll(() => requests.some(url =>
    url.searchParams.get('page_size') !== '1' && url.searchParams.getAll('role_id').includes('none'))).toBe(true)
})

test('users: keyword searches name/phone/email on 查询 and stays out of the address bar', async ({ page }) => {
  const requests: URL[] = []
  await page.route('**/api/v1/system/roles?**', route => respond(route, { items: [], total: 0 }))
  await page.route('**/api/v1/system/users?**', route => {
    requests.push(new URL(route.request().url()))
    return respond(route, { items: [], total: 0 })
  })
  await page.goto('/system/users')
  await page.getByPlaceholder('用户名、姓名、电话或邮箱').fill('13800131001')
  await page.getByRole('button', { name: '查询', exact: true }).click()
  await expect.poll(() => requests.some(url => url.searchParams.get('keyword') === '13800131001')).toBe(true)
  expect(page.url()).not.toContain('13800131001')
})

test('users: excel import shows initial-password note; export carries the applied filters', async ({ page }) => {
  const exports: URL[] = []
  await page.route('**/api/v1/system/roles?**', route => respond(route, { items: [role('1')], total: 1 }))
  await page.route('**/api/v1/system/users?**', route => respond(route, { items: [], total: 0 }))
  await page.route('**/api/v1/system/users/export?**', route => {
    exports.push(new URL(route.request().url()))
    return route.fulfill({ body: 'xlsx', contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  })
  await page.route('**/api/v1/system/users/import', route => route.fulfill({
    body: 'xlsx',
    contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    headers: {
      'Content-Disposition': 'attachment; filename="users-import.xlsx"',
      'X-Import-Inserted': '2', 'X-Import-Skipped': '1', 'X-Import-Total': '3', 'X-Import-Rejected': '0', 'X-Import-Updated': '0',
    },
  }))
  await page.goto('/system/users')

  await page.locator('input[type=file]').setInputFiles({ name: '新同事.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('x') })
  const result = page.getByRole('dialog', { name: '导入完成', exact: true })
  await expect(result.locator('dl')).toContainText('总记录3新增2更新0跳过1')
  await expect(result).toContainText('「初始密码」页是新账号的初始密码，只给这一次')
  await expect(result).toContainText('「跳过的行」页写了每行跳过的原因')
  await result.getByRole('button', { name: '完成', exact: true }).click()
  await expect(result).toHaveCount(0)

  await page.locator('.filter-bar .el-form-item').filter({ hasText: '状态' }).locator('.el-select').click()
  await page.getByRole('option', { name: '禁用' }).click()
  await page.getByRole('button', { name: '查询', exact: true }).click()
  await page.getByRole('button', { name: '下载 Excel' }).click()
  await expect.poll(() => exports.length).toBe(1)
  expect(exports[0].searchParams.getAll('status')).toEqual(['disabled'])
})

test('users: detail drawer shows effective permissions and their source roles', async ({ page }) => {
  await page.route('**/api/v1/system/roles?**', route => respond(route, { items: [role('1')], total: 1 }))
  await page.route('**/api/v1/system/users?**', route => respond(route, {
    items: [{ id: 'u1', username: 'zhangsan', display_name: '张三', status: 'active', version: 1, created_at: '2026-09-23T08:00:00+00:00', roles: [{ id: '1', name: '角色1', status: 'active', is_builtin: false }] }],
    total: 1,
  }))
  await page.route('**/api/v1/system/users/u1', route => respond(route, {
    id: 'u1', username: 'zhangsan', display_name: '张三', status: 'active', version: 1, created_at: '2026-09-23T08:00:00+00:00',
    role_ids: ['1'], roles: [{ id: '1', name: '角色1', status: 'active', is_builtin: false }],
  }))
  await page.route('**/api/v1/system/users/u1/permissions', route => respond(route, {
    account_active: true,
    items: [{ resource_code: 'policy.sources', resource_name: '信源管理', group_name: '政策', level: 'FULL', sources: [{ role_id: '1', role_name: '角色1', level: 'FULL', active: true }] }],
  }))
  await page.goto('/system/users')
  await page.getByRole('button', { name: 'zhangsan', exact: true }).click()
  const drawer = page.locator('.el-drawer')
  await expect(drawer.getByText('实际权限')).toBeVisible()
  await expect(drawer.locator('.perm-line')).toContainText('信源管理')
  await expect(drawer.locator('.perm-line')).toContainText('可管理')
  await expect(drawer.locator('.perm-line')).toContainText('来自 角色1（可管理）')
})
