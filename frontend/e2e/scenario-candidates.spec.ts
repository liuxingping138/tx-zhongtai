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
  industries: [{ path: '交通行业/交通运输、仓储和邮政业/航空', rows: 52 }],
  children: [{ path: '施工进度管理', rows: 12 }],
  reasons: [{ text: '新增二级场景对应建设期数字化管理需求', count: 21 }],
})

test('按场景审核：看来源政策，按建议合并后自动打开下一个', async ({ page }) => {
  let merged: unknown = null
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
      merged = route.request().postDataJSON()
      return respond(route, { ...airport, status: '已合并', version: 2 })
    }
    if (path.endsWith('/context')) {
      return respond(route, {
        siblings: [{ name: '智慧空侧', children: 9 }, { name: '智慧航站楼', children: 7 }],
        similar: [{ path: ['智慧交通工程建设', '交通工程建设信息化'], score: 0.7, level: '高', desc: '交通工程建设信息化通过构建工程管理云平台' }],
        industries: [],
      })
    }
    if (path.endsWith('/rows')) {
      return respond(route, {
        items: [{ id: 'r1', policy_title: '蓝图变实景三晋崛起空港新地标', created_at: '2026-10-26 16:36:20', industry: '交通行业', industry_l1: '交通行业', industry_l2: '', industry_l3: '', scenario_l1_name: '智慧航空', scenario_l2_name: '智慧机场工程建设管理', scenario_l3_name: '', opportunity_type: 'TO_B', remark: '码表无建设期场景', scenario_state: '待审', version: 2 }],
        total: 1, page: 1, page_size: 20,
      })
    }
    if (path.endsWith('/scenario-candidates/c1')) return respond(route, detail(airport))
    if (path.endsWith('/scenario-candidates/c2')) return respond(route, detail(water))
    if (path.endsWith('/scenario-candidates')) {
      // 合并后 c1 出了「待审」，c2 补到同一位置
      const items = merged ? [water] : [airport, water]
      return respond(route, {
        items, total: items.length, page: 1, page_size: 20,
        summary: { by_status: { 待审: items.length }, pending_rows: 115, pending_similar: 1, new_today: 0 },
      })
    }
    return respond(route, { items: [], total: 0, page: 1, page_size: 20 })
  })

  await page.goto('/policy/scenario-candidates')
  await expect(page.getByText('待审 2 个新增场景，涉及 115 行政策解读')).toBeVisible()
  await expect(page.getByRole('radio', { name: /待审 2/ })).toBeChecked()

  await page.getByRole('button', { name: '看提出「智慧机场工程建设管理」的 37 条政策' }).click()
  const drawer = page.locator('.el-drawer')
  await expect(drawer.getByText('蓝图变实景三晋崛起空港新地标')).toBeVisible()
  await drawer.getByRole('button', { name: '改场景' }).click()
  // Element Plus 的下拉框把占位文字画在一个 span 里，不是输入框的 placeholder
  await expect(drawer.getByText('在「交通行业」下搜码表里的场景')).toBeVisible()
  await page.keyboard.press('Escape')

  await page.getByRole('link', { name: '智慧机场工程建设管理' }).first().click()
  await expect(page.getByRole('heading', { name: '智慧机场工程建设管理', level: 1 })).toBeVisible()
  await expect(page.getByText('系统建议 · 码表里有名称很像的')).toBeVisible()
  await expect(page.getByText('＋ 智慧机场工程建设管理')).toBeVisible()

  await page.getByRole('button', { name: '按建议合并…' }).click()
  const dialog = page.getByRole('dialog', { name: '合并到已有场景' })
  await expect(dialog.getByText('已选：智慧交通工程建设 › 交通工程建设信息化')).toBeVisible()
  await dialog.getByRole('button', { name: '确定合并' }).click()

  await expect.poll(() => merged).toEqual({ version: 1, target: ['智慧交通工程建设', '交通工程建设信息化'], rename: false })
  await expect(page.getByRole('heading', { name: '再生水循环利用', level: 1 })).toBeVisible()
  await expect(page.getByText('已合并到已有场景，打开了下一个')).toBeVisible()
})
