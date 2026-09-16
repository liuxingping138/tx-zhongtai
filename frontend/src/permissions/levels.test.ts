import { describe, expect, it } from 'vitest'

import { applyParentLevel, canRead, canWrite, grantDiff, grantsFromTree } from './levels'

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
