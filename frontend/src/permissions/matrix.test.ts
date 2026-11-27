import { describe, expect, it } from 'vitest'

import type { ModuleEntry, ModuleGroup } from './catalog'
import {
  columnState,
  countChangedModules,
  countOpenedModules,
  countTotalModules,
  filterCapabilities,
  filterGroups,
  filterGroupsByStatus,
  isChanged,
  isColumnChecked,
  isModuleChanged,
  openedCount,
  toggleCell,
  toggleGroupColumn,
  type Grants,
} from './matrix'

const entry = (code: string, name: string, levels: ModuleEntry['levels'], downloadCode?: string): ModuleEntry => ({
  code,
  name,
  levels,
  writes: [],
  ...(downloadCode ? { downloadCode } : {}),
})
const sources = entry('policy.sources', '信源管理', ['READ', 'EXPORT', 'FULL'])
const tags = entry('policy.base_tags', '基础标签', ['READ', 'EXPORT', 'FULL'])
const audit = entry('system.audit', '操作日志', ['READ'])
const perms = entry('system.permissions', '权限分配', ['READ', 'FULL'])
const knowledge = entry('thinktank.knowledge', '资料库', ['READ', 'EXPORT', 'FULL'], 'thinktank.knowledge.download')
const reports = entry('thinktank.reports', '报告库', ['READ', 'EXPORT', 'FULL'], 'thinktank.reports.download')
const policy: ModuleGroup = { code: 'policy', name: '政策', modules: [sources, tags] }
const system: ModuleGroup = { code: 'system', name: '系统管理', modules: [audit] }
const thinktank: ModuleGroup = { code: 'thinktank', name: '智库', modules: [knowledge, reports] }

describe('filterGroups', () => {
  it('没有关键词时原样返回', () => {
    expect(filterGroups([policy], '  ')).toEqual([policy])
  })
  it('分组名命中时整组保留，模块名或编码命中时只留命中的行', () => {
    expect(filterGroups([policy, system], '政策')).toEqual([policy])
    expect(filterGroups([policy, system], 'BASE_TAGS')[0]?.modules).toEqual([tags])
    expect(filterGroups([policy, system], '不存在')).toEqual([])
  })
})

describe('filterCapabilities', () => {
  it('特殊能力可以用「分配角色」搜到', () => {
    expect(filterCapabilities([perms], '分配角色')).toEqual([perms])
    expect(filterCapabilities([perms], '信源')).toEqual([])
  })
})

describe('toggleCell', () => {
  it('勾「管理」自动带上低档，取消「查看」整行清空', () => {
    const on = toggleCell(sources, 'FULL', {}, undefined)
    expect(on).toEqual({ 'policy.sources': 'FULL' })
    expect(toggleCell(sources, 'READ', on!, undefined)).toEqual({ 'policy.sources': 'NONE' })
  })
  it('这个菜单没有的操作不能勾', () => {
    expect(toggleCell(audit, 'EXPORT', {}, undefined)).toBeNull()
  })
  it('权限分配只有超级管理员角色能勾', () => {
    expect(toggleCell(perms, 'FULL', {}, 'editor')).toBeNull()
    expect(toggleCell(perms, 'FULL', {}, 'superadmin')).toEqual({ 'system.permissions': 'FULL' })
  })
  it('下载列与导出列完全独立：勾下载自动补查看、取消下载不影响导出、取消查看自动清空下载', () => {
    expect(toggleCell(sources, 'DOWNLOAD', {}, undefined)).toBeNull()
    // 空态勾下载 -> 自动升为 READ + download=READ，且不勾 EXPORT
    const dlOnly = toggleCell(knowledge, 'DOWNLOAD', {}, undefined)!
    expect(dlOnly).toEqual({ 'thinktank.knowledge': 'READ', 'thinktank.knowledge.download': 'READ' })
    expect(isColumnChecked(knowledge, 'DOWNLOAD', dlOnly)).toBe(true)
    expect(isColumnChecked(knowledge, 'EXPORT', dlOnly)).toBe(false)
    // 勾导出不自动开下载；已有导出再取消下载不影响导出
    const exportOnly = toggleCell(knowledge, 'EXPORT', {}, undefined)!
    expect(isColumnChecked(knowledge, 'DOWNLOAD', exportOnly)).toBe(false)
    const both = toggleCell(knowledge, 'DOWNLOAD', exportOnly, undefined)!
    expect(both).toEqual({ 'thinktank.knowledge': 'EXPORT', 'thinktank.knowledge.download': 'READ' })
    const backToExport = toggleCell(knowledge, 'DOWNLOAD', both, undefined)!
    expect(backToExport).toEqual({ 'thinktank.knowledge': 'EXPORT', 'thinktank.knowledge.download': 'NONE' })
    // 取消查看时自动关闭下载
    const cleared = toggleCell(knowledge, 'READ', both, undefined)!
    expect(cleared).toEqual({ 'thinktank.knowledge': 'NONE', 'thinktank.knowledge.download': 'NONE' })
    // 仅改下载也算模块已修改
    expect(isModuleChanged(knowledge, both, exportOnly)).toBe(true)
  })
})

describe('整组一列', () => {
  it('智库整组下载列支持全选、半选与取消', () => {
    expect(columnState(policy, 'DOWNLOAD', {}, undefined).empty).toBe(true)
    const allOn = toggleGroupColumn(thinktank, 'DOWNLOAD', {}, undefined)!
    expect(allOn).toEqual({
      'thinktank.knowledge': 'READ',
      'thinktank.knowledge.download': 'READ',
      'thinktank.reports': 'READ',
      'thinktank.reports.download': 'READ',
    })
    expect(columnState(thinktank, 'DOWNLOAD', allOn, undefined).checked).toBe(true)
    const allOff = toggleGroupColumn(thinktank, 'DOWNLOAD', allOn, undefined)!
    expect(allOff).toEqual({
      'thinktank.knowledge': 'READ',
      'thinktank.knowledge.download': 'NONE',
      'thinktank.reports': 'READ',
      'thinktank.reports.download': 'NONE',
    })
  })
  it('没勾满时全部勾上，已有更高档的保留', () => {
    const grants: Grants = { 'policy.sources': 'FULL' }
    expect(toggleGroupColumn(policy, 'EXPORT', grants, undefined)).toEqual({
      'policy.sources': 'FULL',
      'policy.base_tags': 'EXPORT',
    })
  })
  it('勾满后再点，全部取消这一列', () => {
    const grants: Grants = { 'policy.sources': 'EXPORT', 'policy.base_tags': 'EXPORT' }
    expect(toggleGroupColumn(policy, 'EXPORT', grants, undefined)).toEqual({
      'policy.sources': 'READ',
      'policy.base_tags': 'READ',
    })
  })
  it('整组都没有这项操作时没有可操作的行', () => {
    expect(toggleGroupColumn(system, 'FULL', {}, undefined)).toBeNull()
    expect(columnState(system, 'FULL', {}, undefined).empty).toBe(true)
  })
  it('状态区分全选、半选和未选', () => {
    expect(columnState(policy, 'READ', {}, undefined)).toEqual({ checked: false, indeterminate: false, empty: false })
    expect(columnState(policy, 'READ', { 'policy.sources': 'READ' }, undefined).indeterminate).toBe(true)
    expect(columnState(policy, 'READ', { 'policy.sources': 'READ', 'policy.base_tags': 'FULL' }, undefined).checked).toBe(true)
  })
})

describe('统计', () => {
  it('已开通数不含 NONE', () => {
    expect(openedCount(policy, { 'policy.sources': 'READ', 'policy.base_tags': 'NONE' })).toBe(1)
  })
  it('缺失按 NONE 比较，没变就不算修改', () => {
    expect(isChanged({}, { 'policy.sources': 'NONE' }, 'policy.sources')).toBe(false)
    expect(isChanged({ 'policy.sources': 'READ' }, {}, 'policy.sources')).toBe(true)
  })
  it('支持按全部/已开通/已修改状态联合过滤并统计总数', () => {
    const groups = [policy, system]
    const grants: Grants = { 'policy.sources': 'FULL', 'system.audit': 'READ' }
    const original: Grants = { 'policy.sources': 'READ', 'system.audit': 'READ' }
    expect(countTotalModules(groups)).toBe(3)
    expect(countOpenedModules(groups, grants)).toBe(2)
    expect(countChangedModules(groups, grants, original)).toBe(1)
    expect(filterGroupsByStatus(groups, grants, original, '', 'ALL')).toHaveLength(2)
    expect(filterGroupsByStatus(groups, grants, original, '', 'OPEN').map(g => g.modules.length)).toEqual([1, 1])
    const changedOnly = filterGroupsByStatus(groups, grants, original, '', 'CHANGED')
    expect(changedOnly).toHaveLength(1)
    expect(changedOnly[0]?.modules).toEqual([sources])
  })
})
