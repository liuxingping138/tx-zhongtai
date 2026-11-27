import { describe, expect, it } from 'vitest'

import type { ResourceNode } from '@/api/types'
import {
  capabilityModules,
  formatGrantLevel,
  isChecked,
  isThinktankDownloadCode,
  levelHint,
  lockReason,
  moduleGroups,
  moduleNames,
  toggleColumn,
  writesHint,
} from './catalog'

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
      node({ code: 'policy.crawler_monitoring', name: '爬虫监测', actions: [action('list', 'READ'), action('export', 'EXPORT')] }),
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

  it('不单设权限的菜单写进它跟着的模块，管理员知道给了这个模块也就看得到那几个菜单', () => {
    const audit = { code: 'system.audit', name: '操作日志', levels: ['READ' as const], writes: [] }
    expect(writesHint(audit)).toBe('只读模块，没有新增或修改操作。同时可见「登录日志」菜单')
    expect(writesHint({ ...users, writes: ['新增'] })).toBe('管理包含：新增。同时可见「在线用户」菜单')
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

  it('智库资料库、报告库与方案库的写操作统一展示上传文件与上传标签', () => {
    const ttTree = [
      node({
        code: 'thinktank',
        name: '智库',
        node_type: 'directory',
        children: [
          node({
            code: 'thinktank.reports',
            name: '报告库',
            actions: [action('list', 'READ'), action('export', 'EXPORT'), action('create', 'FULL'), action('upload_tags', 'FULL')],
            children: [
              node({
                code: 'thinktank.reports.download',
                name: '报告库下载',
                actions: [action('download', 'READ')],
              }),
            ],
          }),
          node({
            code: 'thinktank.proposals',
            name: '方案库',
            actions: [action('list', 'READ'), action('create', 'FULL'), action('upload_tags', 'FULL')],
            children: [
              node({
                code: 'thinktank.proposals.download',
                name: '方案库下载',
                actions: [action('download', 'READ')],
              }),
            ],
          }),
        ],
      }),
    ]
    const ttGroups = moduleGroups(ttTree)
    const ttMods = ttGroups[0]!.modules
    expect(writesHint(ttMods[0]!)).toBe('管理包含：上传文件、上传标签')
    expect(writesHint(ttMods[1]!)).toBe('管理包含：上传文件、上传标签')
    expect(ttMods[0]!.downloadCode).toBe('thinktank.reports.download')
    expect(ttMods[1]!.downloadCode).toBe('thinktank.proposals.download')
    expect(isThinktankDownloadCode('thinktank.reports.download')).toBe(true)
    expect(isThinktankDownloadCode('thinktank.reports')).toBe(false)
    expect(formatGrantLevel('thinktank.reports.download', 'READ')).toBe('可下载')
    expect(formatGrantLevel('thinktank.reports.download', 'NONE')).toBe('不可下载')
    expect(moduleNames(ttGroups)['thinktank.reports.download']).toBe('智库 / 报告库（下载原文件）')
    expect(moduleNames(ttGroups)['thinktank.proposals.download']).toBe('智库 / 方案库（下载原文件）')
  })
})
