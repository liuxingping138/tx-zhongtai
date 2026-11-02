import { describe, expect, it } from 'vitest'

import type { CandidateItem } from '@/api/scenarioCandidates'
import { decisionText, pathLabel, splitPath, suggest, summaryText } from './candidates'

function item(extra: Partial<CandidateItem>): CandidateItem {
  return {
    id: 'c1', kind: '新场景', new_level: 2, level_label: '二级', name: '智慧机场工程建设管理',
    scenario_l1: '智慧航空', scenario_l2: '智慧机场工程建设管理', scenario_l3: '', parent: '智慧航空', industry: '',
    status: '待审', adopted_name: '', target: '', target_l1: '', target_l2: '', target_l3: '', reject_reason: '', note: '',
    decided_at: '', decided_by_name: '', row_count: 52, policy_count: 37, industry_count: 1, main_industry: '交通行业',
    sample_title: '', similar_name: '', similar_score: 0, similar_level: '无', first_seen_at: '', last_seen_at: '', version: 1,
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
  it('新的那一级单独拿出来', () => {
    expect(splitPath(item({}))).toEqual({ known: ['智慧航空'], added: '智慧机场工程建设管理' })
    expect(splitPath(item({ kind: '新关联', scenario_l2: '智慧空侧' }))).toEqual({ known: ['智慧航空', '智慧空侧'], added: '' })
  })
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
