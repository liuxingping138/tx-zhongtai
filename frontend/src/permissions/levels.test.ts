import { describe, expect, it } from 'vitest'

import { applyParentLevel, canRead, canWrite, grantDiff, grantsFromTree, roleModuleSummary } from './levels'

const tree = [
  {
    code: 'system',
    published: true,
    node_type: 'directory',
    children: [
      { code: 'system.users', published: true, node_type: 'resource', children: [] },
      { code: 'system.roles', published: true, node_type: 'resource', children: [] },
      { code: 'policy.sources', published: false, node_type: 'resource', children: [] },
    ],
  },
]

describe('permission helpers', () => {
  it('READ 不能写，FULL 能读能写', () => {
    expect(canRead('READ')).toBe(true)
    expect(canWrite('READ')).toBe(false)
    expect(canWrite('FULL')).toBe(true)
  })

  it('父节点批量只更新已发布叶子', () => {
    const next = applyParentLevel(tree[0], 'READ', {})
    expect(next['system.users']).toBe('READ')
    expect(next['system.roles']).toBe('READ')
    expect(next['policy.sources']).toBeUndefined()
  })

  it('变更摘要能对比授权差异', () => {
    const before = grantsFromTree(tree, { 'system.users': 'NONE', 'system.roles': 'READ' })
    const after = grantsFromTree(tree, { 'system.users': 'FULL', 'system.roles': 'READ' })
    expect(grantDiff(before, after)).toEqual([{ code: 'system.users', from: 'NONE', to: 'FULL' }])
  })
})

describe('roleModuleSummary', () => {
  it('全部可管理时不重复数字', () => {
    expect(roleModuleSummary({ read: 0, export: 0, full: 12 })).toBe('12 个模块 · 均可管理')
  })
  it('部分可管理', () => {
    expect(roleModuleSummary({ read: 3, export: 1, full: 2 })).toBe('6 个模块 · 其中 2 个可管理')
  })
  it('没有管理档', () => {
    expect(roleModuleSummary({ read: 2, export: 1, full: 0 })).toBe('3 个模块 · 仅查看或导出')
  })
  it('没有任何授权返回空串，由调用方决定怎么说', () => {
    expect(roleModuleSummary(undefined)).toBe('')
  })
})
