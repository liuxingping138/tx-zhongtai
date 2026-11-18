import { describe, expect, it } from 'vitest'

import { actionLabel, businessLineLabel, directoryLabel, directoryRoots, moduleLabel, modulesInDirectories } from './auditLabels'

describe('auditLabels', () => {
  it('模块编码转中文', () => {
    expect(moduleLabel('policy.sources')).toBe('信源管理')
    expect(moduleLabel('codebook.area_codes')).toBe('省市区编码表')
    expect(moduleLabel('auth')).toBe('登录认证')
  })

  it('动作编码转中文', () => {
    expect(actionLabel('import')).toBe('导入')
    expect(actionLabel('login')).toBe('登录')
    expect(actionLabel('catalog_sync')).toBe('同步清单')
    // 后端真会发的动作码都要有中文，不然日志里直接露出 ask、publish。
    expect([actionLabel('ask'), actionLabel('publish'), actionLabel('sync_scenarios')]).toEqual(['试发 / 样本试跑', '上线 / 下线', '同步新增场景'])
    expect(moduleLabel('ai.releases')).toBe('模板上线')
  })

  it('未知编码原样返回', () => {
    expect(moduleLabel('unknown.module')).toBe('unknown.module')
    expect(actionLabel('unknown')).toBe('unknown')
  })

  it('业务模块取菜单目录，类型取入库时算好的业务线', () => {
    expect(['auth', 'system.users', 'policy.sources', 'codebook.area_codes', 'thinktank.knowledge', 'ai.prompts'].map(directoryLabel))
      .toEqual(['系统管理', '系统管理', '政策', '码表管理', '智库', 'AI提问'])
    expect([businessLineLabel('tender'), businessLineLabel('thinktank'), businessLineLabel(null), businessLineLabel('x')])
      .toEqual(['招投标', '智库', '-', '-'])
  })

  it('业务模块换算成模块编码第一段，模块选项随之收窄', () => {
    expect(directoryRoots(['系统管理', 'AI提问'])).toEqual(['auth', 'iam', 'system', 'ai'])
    const codes = ['auth', 'system.users', 'policy.sources', 'ai.prompts', 'systemx']
    expect(modulesInDirectories(codes, ['系统管理'])).toEqual(['auth', 'system.users'])
    expect(modulesInDirectories(codes, [])).toEqual(codes)
  })
})
