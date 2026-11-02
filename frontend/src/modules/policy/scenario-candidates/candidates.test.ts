import { describe, expect, it } from 'vitest'

import type { CandidateItem } from '@/api/scenarioCandidates'
import { aiText, decisionText, levelTag, levelTitle, matchHeadline, matchItems, matchOf, pathLabel, siblingsText, similarLabel, suggest, summaryText, whereText } from './candidates'

function item(extra: Partial<CandidateItem>): CandidateItem {
  return {
    id: 'c1', kind: '新场景', new_level: 2, level_label: '二级', name: '智慧机场工程建设管理',
    scenario_l1: '智慧航空', scenario_l2: '智慧机场工程建设管理', scenario_l3: '', parent: '智慧航空', industry: '',
    status: '待审', merged_into: '', adopted_name: '', target: '', target_l1: '', target_l2: '', target_l3: '', reject_reason: '', note: '',
    decided_at: '', decided_by_name: '', row_count: 52, policy_count: 37, industry_count: 1, main_industry: '交通行业',
    sample_title: '', similar_name: '', similar_score: 0, similar_level: '无', first_seen_at: '', last_seen_at: '', version: 1,
    ai_verdict: '', ai_similar: '', ai_target: '', ai_reason: '', ai_checked_at: '',
    ...extra,
  }
}

describe('系统建议', () => {
  it('码表里有高度相似的建议合并，不管有多少政策', () => {
    expect(suggest(item({ similar_level: '高', policy_count: 1 }))).toBe('merge')
  })
  it('没有相似、不止一两条政策这么说的建议采纳；只挂到新行业的也建议采纳', () => {
    expect(suggest(item({}))).toBe('adopt')
    expect(suggest(item({ kind: '新关联', policy_count: 1 }))).toBe('adopt')
  })
  it('只有一两条政策提的、相似度一般的不标建议', () => {
    expect(suggest(item({ policy_count: 2 }))).toBeNull()
    expect(suggest(item({ similar_level: '中' }))).toBeNull()
  })
})

describe('文案', () => {
  it('决定写成一句话', () => {
    expect(decisionText(item({ status: '已合并', target: '智慧交通工程建设 › 交通工程建设信息化', decided_by_name: '张三', decided_at: '2026-11-02 10:00:00' })))
      .toBe('已合并到「智慧交通工程建设 › 交通工程建设信息化」，张三 2026-11-02 10:00:00')
    expect(decisionText(item({ status: '已驳回', reject_reason: '说法不对' }))).toBe('已驳回：说法不对')
    expect(decisionText(item({}))).toBe('')
  })
  it('一句话结论只说有的', () => {
    expect(summaryText({ by_status: { 待审: 1024 }, pending_rows: 98312, pending_similar: 312, new_today: 0 }))
      .toBe('待审 1,024 个新增场景，涉及 98,312 行政策解读；其中 312 个和码表已有场景高度相似。')
    expect(summaryText({ by_status: {}, pending_rows: 0, pending_similar: 0, new_today: 0 })).toBe('没有待审的新增场景。')
    expect(summaryText(null)).toBe('')
  })
  it('码表路径带上行业', () => {
    expect(pathLabel({
      industry_scenario_code: 'x', industry_l1: '交通行业', industry_l2: '交通运输', industry_l3: '',
      scenario_l1_name: '智慧航空', scenario_l2_name: '智慧空侧', scenario_l3_name: '',
    })).toBe('智慧航空 › 智慧空侧（交通行业/交通运输）')
  })
})

describe('给业务人员看的说法', () => {
  it('几级、挂在哪一眼看清', () => {
    expect(levelTag(item({}))).toBe('新二级')
    expect(levelTitle(item({}))).toBe('AI 新增的二级场景')
    expect(whereText(item({}))).toBe('交通行业 › 智慧航空 下')
    expect(whereText(item({ new_level: 1, level_label: '一级', parent: '', main_industry: '医卫行业' }))).toBe('医卫行业 · 新的一级场景')
    expect(levelTag(item({ kind: '新关联', level_label: '新关联', industry: '交通行业/道路' }))).toBe('新关联')
    expect(whereText(item({ kind: '新关联', industry: '交通行业/道路' }))).toBe('挂到 交通行业/道路')
  })
  it('同级场景下级多的排前面，多了写「等 N 个」', () => {
    const siblings = [{ name: '智慧陆侧', children: 2 }, { name: '智慧空侧', children: 9 }, { name: '智慧航站楼', children: 7 }, { name: '通航', children: 0 }]
    expect(siblingsText(siblings)).toBe('智慧空侧、智慧航站楼、智慧陆侧 等 4 个')
    expect(siblingsText([])).toBe('')
  })
  it('相似程度写成名称很像、名称有点像、没有', () => {
    expect([similarLabel('高'), similarLabel('中'), similarLabel('无'), similarLabel('')]).toEqual(['名称很像', '名称有点像', '没有', '还没算'])
  })
})

describe('码表里像它的', () => {
  it('AI 说该合并的排第一类，其余按名称相似分，和后端筛选一样每个只落一类', () => {
    expect(matchOf(item({ ai_verdict: '同一个场景', ai_similar: '智慧航空 > 智慧航站楼', similar_level: '高' })))
      .toEqual({ kind: 'ai', label: 'AI 认为是同一个', name: '智慧航空 › 智慧航站楼', note: '' })
    expect(matchOf(item({ ai_verdict: '归到已有场景下', ai_similar: 'a > b' })).label).toBe('AI 认为应归到这里')
    expect(matchOf(item({ ai_verdict: '新场景', similar_level: '中', similar_name: '智慧水务 > 智慧排水' })))
      .toEqual({ kind: 'medium', label: '名称有点像', name: '智慧水务 › 智慧排水', note: 'AI 认为是新场景' })
    expect(matchOf(item({ ai_verdict: '新场景' }))).toEqual({ kind: 'none', label: '没有', name: '', note: 'AI 也认为是新场景' })
    expect(matchOf(item({})).note).toBe('AI 还没看')
  })
  it('审核页列表：AI 认为是同一个的排第一，名称相近里同一个场景不重复列', () => {
    const similar = [
      { path: ['智慧工会', '工程建设管理'], score: 0.5, level: '中', desc: '工会的工程建设', industry: '重要客户服务一部' },
      { path: ['智慧交通工程建设', '交通工程建设信息化'], score: 0.4, level: '中', desc: '交通工程', industry: '交通行业' },
    ]
    const candidate = item({ ai_verdict: '归到已有场景下', ai_similar: '智慧交通工程建设 > 交通工程建设信息化', ai_target: '智慧交通工程建设 > 交通工程建设信息化', ai_reason: '太细' })
    const items = matchItems(candidate, similar)
    expect(items.map(row => [row.badge, row.text, row.ai])).toEqual([
      ['AI 认为应归到这里', '智慧交通工程建设 › 交通工程建设信息化', true],
      ['名称有点像', '智慧工会 › 工程建设管理', false],
    ])
    expect(items[0]).toMatchObject({ path: ['智慧交通工程建设', '交通工程建设信息化'], note: '二级场景 · 交通行业 · 同一个行业', detail: 'AI：太细' })
    expect(items[1]?.note).toBe('二级场景 · 重要客户服务一部 · 不是同一个行业，多半不是一回事')
    expect(matchHeadline(candidate, items)).toBe('找到 2 个，AI 认为是同一个的排在最前')
  })
  it('AI 说的名字码表里对不上：照样列出来，但不能直接合并', () => {
    const items = matchItems(item({ ai_verdict: '同一个场景', ai_similar: '智慧机场' }), [])
    expect(items).toEqual([{ path: null, text: '智慧机场', badge: 'AI 认为是同一个', ai: true, note: '码表里没对上这个名字，请自己在码表里选', detail: '' }])
  })
  it('AI 认为是新场景、还没看过时，名称相近的只是参考', () => {
    const similar = [{ path: ['智慧水务', '智慧排水'], score: 0.4, level: '中', desc: '', industry: '能源行业' }]
    expect(matchHeadline(item({ ai_verdict: '新场景' }), matchItems(item({ ai_verdict: '新场景' }), similar)))
      .toBe('AI 对照了同一行业的场景，认为码表里没有同样的；下面 1 个只是名称相近，供参考')
    expect(matchHeadline(item({}), [])).toBe('AI 还没看过（任务调度里「新增场景找相似」跑过后才有）；名称相近的也没有')
  })
})

describe('AI 找相似', () => {
  it('AI 看过的按 AI 的判断建议，码表里对得上才建议合并', () => {
    expect(suggest(item({ ai_verdict: '同一个场景', ai_similar: '智慧航空 > 智慧航站楼', ai_target: '智慧航空 > 智慧航站楼' }))).toBe('merge')
    expect(suggest(item({ ai_verdict: '同一个场景', ai_similar: '智慧机场' }))).toBeNull()
    expect(suggest(item({ ai_verdict: '新场景', similar_level: '高', policy_count: 1 }))).toBe('adopt')
  })
  it('解读核对页卡片上的一句话', () => {
    expect(aiText(item({}))).toMatch(/^AI 还没看过/)
    expect(aiText(item({ ai_verdict: '新场景', ai_reason: '码表没有建设期管理' }))).toBe('AI 判断：新场景。理由：码表没有建设期管理')
    expect(aiText(item({ ai_verdict: '同一个场景', ai_similar: 'a > b' }))).toBe('AI 判断：同一个场景，最像的是「a › b」')
  })
})
