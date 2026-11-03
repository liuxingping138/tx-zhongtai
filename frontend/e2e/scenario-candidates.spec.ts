import { expect, test, type Route } from '@playwright/test'

const respond = (route: Route, data: unknown) => route.fulfill({ json: { code: 'OK', data } })

const base = {
  kind: '新场景', new_level: 2, level_label: '二级', scenario_l3: '', industry: '', adopted_name: '',
  target: '', target_l1: '', target_l2: '', target_l3: '', reject_reason: '', note: '', decided_at: '', decided_by_name: '',
  industry_count: 1, main_industry: '交通行业', sample_title: '', similar_score: 0.7,
  first_seen_at: '2026-10-26 16:36:20', last_seen_at: '2026-11-01 09:00:00', status: '待审', version: 1,
}
const airport = {
  ...base, id: 'c1', name: '智慧机场工程建设管理', scenario_l1: '智慧航空', scenario_l2: '智慧机场工程建设管理',
  parent: '智慧航空', row_count: 52, policy_count: 37, similar_name: '智慧交通工程建设 > 交通工程建设信息化', similar_level: '高',
}
const water = {
  ...base, id: 'c2', name: '再生水循环利用', scenario_l1: '智慧水务', scenario_l2: '再生水循环利用', parent: '智慧水务',
  main_industry: '能源行业', row_count: 63, policy_count: 58, similar_name: '', similar_level: '无',
}
const detail = (item: Record<string, unknown>) => ({
  ...item,
  industries: [{ path: '交通行业/交通运输、仓储和邮政业/航空', names: ['交通行业', '交通运输、仓储和邮政业', '航空'], rows: 52 }],
  children: [{ path: '施工进度管理', rows: 12 }],
  reasons: [{ text: '新增二级场景对应建设期数字化管理需求', count: 21 }],
})

type Mocks = { merged: unknown; adopted: unknown; batchAdopted: unknown }

const interpretation = {
  id: 'i1', policy_title: '蓝图变实景三晋崛起空港新地标', data_status: '待验证', version: 2, candidate_id: 'c1', scenario_state: '待审',
  industry_l1: '交通行业', scenario_l1_name: '智慧航空', scenario_l2_name: '智慧机场工程建设管理', is_new_scenario: '是',
}

/** 待审两个场景：机场（码表里有名称很像的）、再生水（没有像的）。合并后机场出列表。 */
async function mockCandidates(page: import('@playwright/test').Page, seen: Mocks) {
  await page.route('**/api/v1/**', (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (path.endsWith('/auth/csrf')) return respond(route, { csrf_token: 'test' })
    if (path.endsWith('/auth/refresh')) return respond(route, { access_token: 'test', expires_in: 3600, must_change_password: false })
    if (path.endsWith('/auth/me')) return respond(route, { id: 'admin', username: 'admin', display_name: '测试管理员', status: 'active', roles: ['超级管理员'] })
    if (path.endsWith('/auth/permissions')) {
      return respond(route, {
        resources: ['policy.scenario_candidates', 'policy.interpretations', 'codebook.scenarios'].map(code => ({ code, level: 'FULL' })),
        menus: [{ id: 'm', parent_id: null, title: '新增场景审核', route_name: 'policy-scenario-candidates', resource_code: 'policy.scenario_candidates', sort_order: 1 }],
      })
    }
    if (path.endsWith('/scenario-candidates/options')) {
      return respond(route, { options: { level_label: { items: ['一级', '二级'], truncated: false } }, reject_reasons: [] })
    }
    if (path.endsWith('/scenario-candidates/c1/merge')) {
      seen.merged = route.request().postDataJSON()
      return respond(route, { ...airport, status: '已合并', version: 2 })
    }
    if (path.endsWith('/scenario-candidates/c2/adopt')) {
      seen.adopted = route.request().postDataJSON()
      return respond(route, { ...water, status: '已采纳', version: 2 })
    }
    if (path.endsWith('/scenario-candidates/batch-adopt')) {
      seen.batchAdopted = route.request().postDataJSON()
      return respond(route, { done: 1, skipped: [] })
    }
    if (path.endsWith('/context')) {
      return respond(route, {
        siblings: [{ name: '智慧空侧', children: 9 }, { name: '智慧航站楼', children: 7 }],
        similar: [{ path: ['智慧交通工程建设', '交通工程建设信息化'], score: 0.7, level: '高', desc: '交通工程建设信息化通过构建工程管理云平台', industry: '交通行业' }],
        industries: [],
      })
    }
    if (path.endsWith('/peers')) return respond(route, { items: [] })
    if (path.endsWith('/rows')) {
      return respond(route, {
        items: [{ id: 'r1', policy_title: '蓝图变实景三晋崛起空港新地标', created_at: '2026-10-26 16:36:20', industry: '交通行业', industry_l1: '交通行业', industry_l2: '', industry_l3: '', scenario_l1_name: '智慧航空', scenario_l2_name: '智慧机场工程建设管理', scenario_l3_name: '', opportunity_type: 'TO_B', remark: '码表无建设期场景', scenario_state: '待审', version: 2 }],
        total: 1, page: 1, page_size: 20,
      })
    }
    // 解读核对页：这一行的场景就是待审的机场
    if (path.endsWith('/policy/interpretations/i1/content')) return route.fulfill({ status: 404, json: { code: 'RESOURCE_NOT_FOUND', message: '没有正文' } })
    if (path.endsWith('/policy/interpretations/i1')) return respond(route, interpretation)
    if (path.endsWith('/policy/interpretations')) return respond(route, { items: [interpretation], total: 1, page: 1, page_size: 20 })
    if (path.endsWith('/scenario-candidates/c1')) return respond(route, detail(airport))
    if (path.endsWith('/scenario-candidates/c2')) return respond(route, detail(water))
    if (path.endsWith('/scenario-candidates')) {
      const items = seen.merged ? [water] : [airport, water]
      return respond(route, {
        items, total: items.length, page: 1, page_size: 20,
        summary: { by_status: { 待审: items.length }, pending_rows: 115, pending_similar: 1, new_today: 0 },
      })
    }
    return respond(route, { items: [], total: 0, page: 1, page_size: 20 })
  })
}

test('在列表行上审核：展开看依据，合并到这一行写着的场景，改个名再采纳', async ({ page }) => {
  const seen: Mocks = { merged: null, adopted: null, batchAdopted: null }
  await mockCandidates(page, seen)

  await page.goto('/policy/scenario-candidates')
  await expect(page.getByText('待审 2 个新增场景，涉及 115 行政策解读')).toBeVisible()
  const airportRow = page.getByRole('row', { name: /智慧机场工程建设管理/ }).first()
  await expect(airportRow.getByText('名称很像')).toBeVisible()
  // 只露出系统建议的那个：名称很像，建议「合并到它」；其余收在「其他」里
  const decide = page.getByRole('group', { name: '决定「智慧机场工程建设管理」' })
  await expect(decide.getByRole('button', { name: '合并到它' })).toHaveClass(/el-button--primary/)
  await expect(decide.getByRole('button', { name: '其他' })).toBeVisible()

  // 点名称展开：左边码表里像它的，右边同一位置已有、AI 的理由、涉及哪些行业
  await page.getByRole('button', { name: '智慧机场工程建设管理', exact: true }).click()
  const matches = page.getByRole('region', { name: '码表里像「智慧机场工程建设管理」的场景' })
  await expect(matches.getByText('智慧交通工程建设 › 交通工程建设信息化')).toBeVisible()
  await expect(matches.getByRole('button', { name: '合并到这里' })).toBeVisible()
  await expect(page.getByText('智慧航空 下已有')).toBeVisible()
  await expect(page.getByText('智慧空侧、智慧航站楼')).toBeVisible()
  await expect(page.getByText('新增二级场景对应建设期数字化管理需求')).toBeVisible()
  await expect(page.getByText('涉及哪些行业（1 个）')).toBeVisible()

  await page.getByRole('button', { name: '看全部 37 条政策' }).click()
  const drawer = page.locator('.el-drawer')
  await expect(drawer.getByText('蓝图变实景三晋崛起空港新地标')).toBeVisible()
  await drawer.getByRole('button', { name: '改场景' }).click()
  // Element Plus 的下拉框把占位文字画在一个 span 里，不是输入框的 placeholder
  await expect(drawer.getByText('在「交通行业」下搜码表里的场景')).toBeVisible()
  await page.keyboard.press('Escape')

  await decide.getByRole('button', { name: '合并到它' }).click()
  const dialog = page.getByRole('dialog', { name: '合并到已有场景' })
  await expect(dialog.getByText('智慧交通工程建设 › 交通工程建设信息化', { exact: true })).toBeVisible()
  await expect(dialog.getByText('以后 AI 再写「智慧机场工程建设管理」，自动归到这里')).toBeVisible()
  await dialog.getByRole('button', { name: '确定合并' }).click()
  await expect.poll(() => seen.merged).toEqual({ version: 1, target: ['智慧交通工程建设', '交通工程建设信息化'], rename: false })
  await expect(page.getByText('「智慧机场工程建设管理」已合并到已有场景，提出它的 52 行解读一起改好了')).toBeVisible()
  await expect(page.getByRole('button', { name: '智慧机场工程建设管理', exact: true })).toHaveCount(0)

  const water = page.getByRole('group', { name: '决定「再生水循环利用」' })
  await expect(water.getByRole('button', { name: '采纳为新场景' })).toBeVisible()
  await water.getByRole('button', { name: '其他' }).click()
  await page.getByRole('menuitem', { name: '改个名再采纳' }).click()
  const rename = page.getByRole('dialog', { name: '改个名再采纳' })
  const confirm = rename.getByRole('button', { name: '采纳并写进码表' })
  // 名字没改不能提交（那就是直接采纳）
  await expect(confirm).toBeDisabled()
  await rename.getByLabel('场景名称（AI 写的是「再生水循环利用」）').fill('再生水利用')
  await expect(rename.getByText('提出它的 63 行解读改成这个名字并回填编码')).toBeVisible()
  await confirm.click()
  await expect.poll(() => seen.adopted).toEqual({ version: 1, name: '再生水利用' })
})

test('旧的单个场景地址转到列表并展开那一行；勾选后批量采纳，确认框列出每个场景', async ({ page }) => {
  const seen: Mocks = { merged: null, adopted: null, batchAdopted: null }
  await mockCandidates(page, seen)

  await page.goto('/policy/scenario-candidates/c2')
  await expect(page).toHaveURL(/\/policy\/scenario-candidates\?/)
  await expect(page.getByRole('region', { name: '码表里像「再生水循环利用」的场景' })).toBeVisible()

  // Element Plus 的原生勾选框是隐藏的，点可见的那个框
  await page.getByRole('row', { name: /再生水循环利用/ }).first().locator('.el-checkbox').click()
  await page.getByRole('button', { name: '批量采纳' }).click()
  const dialog = page.getByRole('dialog', { name: '批量采纳为新场景' })
  await expect(dialog.getByText('再生水循环利用', { exact: true })).toBeVisible()
  await expect(dialog.getByText('新二级 · 能源行业 › 智慧水务 下')).toBeVisible()
  await dialog.getByRole('button', { name: '采纳这 1 个' }).click()
  await expect.poll(() => seen.batchAdopted).toEqual({ items: [{ id: 'c2', version: 1 }] })
})

test('解读核对页：场景还在待审时，「行业与场景」里只占一行，页签上有提醒，按钮和列表一样', async ({ page }) => {
  const seen: Mocks = { merged: null, adopted: null, batchAdopted: null }
  await mockCandidates(page, seen)

  await page.goto('/policy/interpretations/i1')
  const line = page.getByRole('region', { name: '行业与场景' }).getByRole('region', { name: '这一行的新增场景' })
  await expect(line.getByText('新二级 · 待审')).toBeVisible()
  await expect(line.getByText('37 条政策 · 码表里名称很像：智慧交通工程建设 › 交通工程建设信息化 · AI 还没看')).toBeVisible()
  // 停在别的分组也知道：「行业与场景」页签旁有个提醒点
  await expect(page.getByRole('navigation', { name: '详情分组' }).getByRole('button', { name: /行业与场景.*这一行的场景还在新增场景审核里待审/ })).toBeVisible()

  await line.getByRole('button', { name: '合并到它' }).click()
  const dialog = page.getByRole('dialog', { name: '合并到已有场景' })
  await expect(dialog.getByText('智慧交通工程建设 › 交通工程建设信息化', { exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: '确定合并' }).click()
  await expect.poll(() => seen.merged).toEqual({ version: 1, target: ['智慧交通工程建设', '交通工程建设信息化'], rename: false })
})

test('补充待确认：核对 AI 写的描述，改好后确认，接着看下一个', async ({ page }) => {
  let confirmed: unknown = null
  const item = (name: string, desc: string) => ({
    key: `智慧航空 > ${name}`, path: ['智慧航空', name], level: 2, industries: ['交通行业/交通运输、仓储和邮政业/航空'],
    rows: 2, source_policy: '蓝图变实景三晋崛起空港新地标', desc_90: desc, desc_130: '', desc_pest: '', level_desc: '',
  })
  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/csrf')) return respond(route, { csrf_token: 'test' })
    if (path.endsWith('/auth/refresh')) return respond(route, { access_token: 'test', expires_in: 3600, must_change_password: false })
    if (path.endsWith('/auth/me')) return respond(route, { id: 'admin', username: 'admin', display_name: '测试管理员', status: 'active', roles: ['超级管理员'] })
    if (path.endsWith('/auth/permissions')) {
      return respond(route, {
        resources: ['policy.scenario_candidates', 'codebook.scenarios'].map(code => ({ code, level: 'FULL' })),
        menus: [{ id: 'm', parent_id: null, title: '新增场景审核', route_name: 'policy-scenario-candidates', resource_code: 'policy.scenario_candidates', sort_order: 1 }],
      })
    }
    if (path.endsWith('/scenarios/enrich-pending')) {
      return respond(route, { items: confirmed ? [item('施工管理', '')] : [item('智慧机场工程建设管理', 'AI 写的描述'), item('施工管理', '')] })
    }
    if (path.endsWith('/scenarios/enrich-confirm')) {
      confirmed = route.request().postDataJSON()
      return respond(route, { rows: 2 })
    }
    if (path.endsWith('/scenario-candidates')) {
      return respond(route, { items: [], total: 0, page: 1, page_size: 20, summary: { by_status: {}, pending_rows: 0, pending_similar: 0, new_today: 0 } })
    }
    return respond(route, { items: [], total: 0, page: 1, page_size: 20 })
  })

  await page.goto('/policy/scenario-candidates')
  // Element Plus 的单选按钮原生输入框是隐藏的，点可见的标签
  await page.locator('.el-radio-button').filter({ hasText: /补充待确认 2/ }).click()
  await expect(page.getByRole('heading', { name: '智慧航空 › 智慧机场工程建设管理' })).toBeVisible()
  const desc = page.getByLabel('场景描述（90字）')
  await expect(desc).toHaveValue('AI 写的描述')
  await desc.fill('改过的描述')
  await page.getByRole('button', { name: '确认无误，下一个' }).click()
  await expect.poll(() => confirmed).toMatchObject({ path: ['智慧航空', '智慧机场工程建设管理'], desc_90: '改过的描述' })
  await expect(page.getByRole('heading', { name: '智慧航空 › 施工管理' })).toBeVisible()
  await expect(page.getByText('AI 没写出来，请自己补上。')).toBeVisible()
  await expect(page.locator('.el-radio-button').filter({ hasText: /补充待确认 1/ })).toBeVisible()
})
