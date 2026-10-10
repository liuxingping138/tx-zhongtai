import { describe, expect, it } from 'vitest'

import type { ResourceNode } from '@/api/types'
import { capabilityModules, isChecked, levelHint, lockReason, moduleGroups, moduleNames, toggleColumn, writesHint } from './catalog'

function node(partial: Partial<ResourceNode> & Pick<ResourceNode, 'code' | 'name'>): ResourceNode {
  return {
    id: partial.code,
    service_code: 's',
    node_type: 'resource',
    published: true,
    sort_order: 0,
    parent_id: null,
    actions: [],
    children: [],
    ...partial,
  }
}

const action = (action_code: string, required_level: string) => ({ action_code, required_level })

const tree: ResourceNode[] = [
  node({
    code: 'policy',
    name: '政策',
    node_type: 'directory',
    children: [
      node({
        code: 'policy.sources',
        name: '信源管理',
        // 故意打乱顺序：后端按编码字母序返回，页面要按「先增后改」展示。
        actions: [action('purge', 'FULL'), action('export', 'EXPORT'), action('import', 'FULL'), action('list', 'READ'), action('update', 'FULL'), action('create', 'FULL'), action('read', 'READ')],
      }),
      node({ code: 'policy.crawler_monitoring_v2', name: '爬虫监测', actions: [action('list', 'READ'), action('export', 'EXPORT')] }),
      node({ code: 'system.users', name: '用户管理', actions: [action('list', 'READ'), action('create', 'FULL')] }),
    ],
  }),
  node({ code: 'customer', name: '客户', node_type: 'directory', published: false, children: [] }),
  node({
    code: 'tender',
    name: '招投标',
    node_type: 'directory',
    children: [node({ code: 'tender.bids', name: '标讯', published: false })],
  }),
]

// 用例数据固定，这三项一定存在；取不到时让测试直接报错。
const modules = moduleGroups(tree)[0]!.modules
const sources = modules[0]!
const crawler = modules[1]!
const users = modules[2]!

describe('moduleGroups', () => {
  it('只保留已发布模块，未开发的目录整组不出现', () => {
    const groups = moduleGroups(tree)
    expect(groups.map(group => group.name)).toEqual(['政策'])
    expect(groups[0]!.modules.map(module => module.name)).toEqual(['信源管理', '爬虫监测', '用户管理'])
  })

  it('按模块实际动作给档位：没有导出就没有「导出」，没有写操作就没有「管理」', () => {
    expect(sources.levels).toEqual(['NONE', 'READ', 'EXPORT', 'FULL'])
    expect(crawler.levels).toEqual(['NONE', 'READ', 'EXPORT'])
    expect(users.levels).toEqual(['NONE', 'READ', 'FULL'])
  })
})

describe('勾选规则', () => {
  it('勾后面的列自动包含前面的列', () => {
    expect(toggleColumn(sources, 'NONE', 'FULL')).toBe('FULL')
    expect(isChecked('FULL', 'READ')).toBe(true)
    expect(isChecked('FULL', 'EXPORT')).toBe(true)
  })

  it('取消某一列降到比它低的最高一档', () => {
    expect(toggleColumn(sources, 'FULL', 'FULL')).toBe('EXPORT')
    expect(toggleColumn(sources, 'FULL', 'EXPORT')).toBe('READ')
    expect(toggleColumn(sources, 'EXPORT', 'READ')).toBe('NONE')
  })

  it('没有导出档的模块取消「管理」直接回到仅查看', () => {
    expect(toggleColumn(users, 'FULL', 'FULL')).toBe('READ')
  })
})

describe('说明文字', () => {
  it('「管理」按先增后改列出具体操作，清空标明仅超级管理员', () => {
    expect(writesHint(sources)).toBe('管理包含：新增、编辑、导入 Excel、清空全表（仅超级管理员）')
    expect(writesHint(crawler)).toBe('只读模块，没有新增或修改操作')
  })

  it('每一档的一句话说明', () => {
    expect(levelHint(sources, 'NONE')).toBe('看不到这个模块')
    expect(levelHint(sources, 'READ')).toBe('可查看')
    expect(levelHint(sources, 'EXPORT')).toBe('可查看、导出 Excel')
    expect(levelHint(users, 'FULL')).toBe('可查看，还可新增')
  })
})

describe('lockReason', () => {
  it('「权限分配」只能属于超级管理员', () => {
    expect(lockReason('system.permissions', 'role-abc')).toContain('只能属于超级管理员')
    expect(lockReason('system.permissions', 'superadmin')).toBe('')
    expect(lockReason('policy.sources', 'role-abc')).toBe('')
  })
})

describe('capabilityModules', () => {
  it('「分配角色」不混进菜单分组', () => {
    const withGrant = [
      node({
        code: 'system',
        name: '系统管理',
        node_type: 'directory',
        children: [
          node({ code: 'system.users', name: '用户管理', actions: [action('list', 'READ')] }),
          node({ code: 'system.permissions', name: '权限分配', actions: [action('read', 'READ'), action('grant', 'FULL')] }),
        ],
      }),
    ]
    expect(moduleGroups(withGrant)[0]!.modules.map(module => module.name)).toEqual(['用户管理'])
    expect(capabilityModules(withGrant).map(module => module.name)).toEqual(['分配角色'])
  })
})

describe('moduleNames', () => {
  it('确认弹窗用「分组 / 模块」的中文名，不显示资源编码', () => {
    expect(moduleNames(moduleGroups(tree))['policy.sources']).toBe('政策 / 信源管理')
  })
})
