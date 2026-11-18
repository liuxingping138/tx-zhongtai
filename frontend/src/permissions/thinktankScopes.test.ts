import { describe, expect, it } from 'vitest'

import type { ResourceNode } from '@/api/types'
import { moduleGroups } from './catalog'
import {
  applyDimensionAllMode,
  capDimensionToMenuLevel,
  collapseScopeDiffs,
  isDimensionAllMode,
  isThinktankScopeCode,
  syncThinktankScopesWithMenu,
  thinktankLibraries,
  thinktankScopeNames,
} from './thinktankScopes'

const SAMPLE_TREE: ResourceNode[] = [
  {
    id: '1',
    code: 'thinktank',
    name: '智库',
    service_code: 'thinktank-service',
    node_type: 'directory',
    published: true,
    sort_order: 45,
    parent_id: null,
    actions: [],
    children: [
      {
        id: '2',
        code: 'thinktank.knowledge',
        name: '知识库',
        service_code: 'thinktank-service',
        node_type: 'resource',
        published: true,
        sort_order: 451,
        parent_id: '1',
        actions: [
          { action_code: 'list', required_level: 'READ' },
          { action_code: 'export', required_level: 'EXPORT' },
          { action_code: 'create', required_level: 'FULL' },
        ],
        children: [
          {
            id: '3',
            code: 'thinktank.knowledge.file_type',
            name: '文件类型范围',
            service_code: 'thinktank-service',
            node_type: 'directory',
            published: true,
            sort_order: 458,
            parent_id: '2',
            actions: [],
            children: [
              {
                id: '4',
                code: 'thinktank.file_type.product',
                name: '文件类型：产品',
                service_code: 'thinktank-service',
                node_type: 'resource',
                published: true,
                sort_order: 460,
                parent_id: '3',
                actions: [
                  { action_code: 'list', required_level: 'READ' },
                  { action_code: 'export', required_level: 'EXPORT' },
                  { action_code: 'update', required_level: 'FULL' },
                ],
                children: [],
              },
              {
                id: '5',
                code: 'thinktank.file_type.undefined',
                name: '文件类型：未定义',
                service_code: 'thinktank-service',
                node_type: 'resource',
                published: true,
                sort_order: 461,
                parent_id: '3',
                actions: [
                  { action_code: 'list', required_level: 'READ' },
                  { action_code: 'export', required_level: 'EXPORT' },
                  { action_code: 'update', required_level: 'FULL' },
                ],
                children: [],
              },
            ],
          },
          {
            id: '6',
            code: 'thinktank.knowledge.industry_type',
            name: '行业类型范围',
            service_code: 'thinktank-service',
            node_type: 'directory',
            published: true,
            sort_order: 459,
            parent_id: '2',
            actions: [],
            children: [
              {
                id: '7',
                code: 'thinktank.industry_type.sme',
                name: '行业类型：中小',
                service_code: 'thinktank-service',
                node_type: 'resource',
                published: true,
                sort_order: 480,
                parent_id: '6',
                actions: [
                  { action_code: 'list', required_level: 'READ' },
                  { action_code: 'export', required_level: 'EXPORT' },
                  { action_code: 'update', required_level: 'FULL' },
                ],
                children: [],
              },
            ],
          },
        ],
      },
    ],
  },
]

describe('thinktankScopes', () => {
  it('separates menu module from thinktank data scope dimensions', () => {
    const menus = moduleGroups(SAMPLE_TREE)
    expect(menus).toHaveLength(1)
    expect(menus[0]?.modules.map(m => m.code)).toEqual(['thinktank.knowledge'])

    const libs = thinktankLibraries(SAMPLE_TREE)
    expect(libs).toHaveLength(1)
    const lib = libs[0]!
    expect(lib.code).toBe('thinktank.knowledge')
    expect(lib.dimensions.map(d => d.name)).toEqual(['文件类型范围', '行业类型范围'])
    expect(lib.dimensions[0]?.modules.map(m => m.name)).toEqual(['产品', '未定义'])
    expect(lib.dimensions[1]?.modules.map(m => m.name)).toEqual(['中小'])

    expect(isThinktankScopeCode('thinktank.file_type.product')).toBe(true)
    expect(isThinktankScopeCode('thinktank.industry_type.sme')).toBe(true)
    expect(isThinktankScopeCode('thinktank.knowledge')).toBe(false)

    const names = thinktankScopeNames(libs)
    expect(names['thinktank.file_type.product']).toBe('智库·知识库 / 文件类型范围：产品')
  })

  it('auto-syncs scope dimensions when menu permission is opened, lowered, or closed', () => {
    const libs = thinktankLibraries(SAMPLE_TREE)
    const fileTypeDim = libs[0]!.dimensions[0]!
    const initial = {
      'thinktank.knowledge': 'NONE' as const,
      'thinktank.file_type.product': 'NONE' as const,
      'thinktank.file_type.undefined': 'NONE' as const,
      'thinktank.industry_type.sme': 'NONE' as const,
    }

    // 开通菜单权限 FULL -> 默认将全空维度同步为 FULL（全部范围模式）
    const opened = syncThinktankScopesWithMenu(libs, initial, {
      ...initial,
      'thinktank.knowledge': 'FULL',
    })
    expect(opened['thinktank.file_type.product']).toBe('FULL')
    expect(opened['thinktank.file_type.undefined']).toBe('FULL')
    expect(opened['thinktank.industry_type.sme']).toBe('FULL')
    expect(isDimensionAllMode(fileTypeDim, opened, 'FULL')).toBe(true)

    // 自定义修改某一项后不再是 ALL 模式，当菜单降档为 READ 时将高于 READ 的项收敛为 READ
    const custom = { ...opened, 'thinktank.file_type.undefined': 'READ' as const }
    expect(isDimensionAllMode(fileTypeDim, custom, 'FULL')).toBe(false)

    const lowered = syncThinktankScopesWithMenu(libs, custom, {
      ...custom,
      'thinktank.knowledge': 'READ',
    })
    expect(lowered['thinktank.file_type.product']).toBe('READ')
    expect(lowered['thinktank.file_type.undefined']).toBe('READ')
    expect(lowered['thinktank.industry_type.sme']).toBe('READ')

    // 一键切回 ALL 模式
    const restoredAll = applyDimensionAllMode(fileTypeDim, custom, 'FULL')
    expect(isDimensionAllMode(fileTypeDim, restoredAll, 'FULL')).toBe(true)

    // 关闭子库菜单 -> 清空全部数据范围
    const closed = syncThinktankScopesWithMenu(libs, opened, {
      ...opened,
      'thinktank.knowledge': 'NONE',
    })
    expect(closed['thinktank.file_type.product']).toBe('NONE')
    expect(closed['thinktank.industry_type.sme']).toBe('NONE')

    // 按菜单档位封顶维度内可选档位
    const capped = capDimensionToMenuLevel(fileTypeDim, 'READ')
    expect(capped.modules[0]?.levels).toEqual(['NONE', 'READ'])

    // 整组同档位变化折叠为 1 条摘要
    const collapsed = collapseScopeDiffs(libs, [
      { code: 'thinktank.knowledge', from: 'NONE', to: 'FULL' },
      { code: 'thinktank.file_type.product', from: 'NONE', to: 'FULL' },
      { code: 'thinktank.file_type.undefined', from: 'NONE', to: 'FULL' },
      { code: 'thinktank.industry_type.sme', from: 'NONE', to: 'FULL' },
    ])
    expect(collapsed).toHaveLength(3)
    expect(collapsed[1]?.label).toBe('智库·知识库 / 文件类型范围（全部 2 项）')
    expect(collapsed[2]?.label).toBe('智库·知识库 / 行业类型范围（全部 1 项）')
  })
})
