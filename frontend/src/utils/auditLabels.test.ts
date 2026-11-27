import { describe, expect, it } from 'vitest'

import { actionLabel, businessLineLabel, directoryLabel, directoryRoots, moduleLabel, modulesInDirectories } from './auditLabels'

describe('auditLabels', () => {
  it('模块编码转中文', () => {
    expect(moduleLabel('policy.sources')).toBe('信源管理')
    expect(moduleLabel('codebook.area_codes')).toBe('省市区编码表')
    expect(moduleLabel('auth')).toBe('登录认证')
    expect([
      moduleLabel('tender.bidding'),
      moduleLabel('tender.winning'),
      moduleLabel('tender.purchaser'),
      moduleLabel('tender.winbid'),
      moduleLabel('tender.statistics'),
    ]).toEqual(['招标信息', '中标信息', '招标基础数据', '中标基础数据', '招标统计分析'])
    expect([
      moduleLabel('thinktank.knowledge'),
      moduleLabel('thinktank.reports'),
      moduleLabel('thinktank.proposals'),
      moduleLabel('thinktank.favorites'),
    ]).toEqual(['资料库', '报告库', '方案库', '我的收藏'])
    expect([
      moduleLabel('codebook.thinktank_file_types'),
      moduleLabel('codebook.thinktank_departments'),
      moduleLabel('codebook.thinktank_industries'),
      moduleLabel('codebook.thinktank_product_types'),
      moduleLabel('codebook.thinktank_provinces'),
      moduleLabel('codebook.thinktank_market_categories'),
    ]).toEqual(['文件类别码表', '客户部门归属码表', '行业类别码表', '产品类别码表', '省份码表', '市场类别码表'])
  })

  it('动作编码转中文', () => {
    expect(actionLabel('import')).toBe('导入')
    expect(actionLabel('login')).toBe('登录')
    expect(actionLabel('catalog_sync')).toBe('同步清单')
    expect(actionLabel('unlock_ip')).toBe('解除 IP 限制')
    // 后端真会发的动作码都要有中文，不然日志里直接露出 ask、publish。
    expect([actionLabel('ask'), actionLabel('publish'), actionLabel('sync_scenarios'), actionLabel('upload_tags')])
      .toEqual(['试发 / 样本试跑', '上线 / 下线', '同步新增场景', '上传标签'])
    expect(moduleLabel('ai.releases')).toBe('模板上线')
  })

  it('未知编码原样返回', () => {
    expect(moduleLabel('unknown.module')).toBe('unknown.module')
    expect(actionLabel('unknown')).toBe('unknown')
  })

  it('业务模块取菜单目录，类型取入库时算好的业务线', () => {
    expect([
      'auth', 'system.users', 'policy.sources', 'codebook.area_codes',
      'codebook.thinktank_file_types', 'codebook.thinktank_provinces',
      'thinktank.knowledge', 'thinktank.reports', 'thinktank.proposals', 'thinktank.favorites',
      'ai.prompts',
    ].map(directoryLabel))
      .toEqual(['系统管理', '系统管理', '政策', '码表管理', '码表管理', '码表管理', '智库', '智库', '智库', '智库', 'AI提问'])
    expect([businessLineLabel('tender'), businessLineLabel('thinktank'), businessLineLabel(null), businessLineLabel('x')])
      .toEqual(['招投标', '智库', '-', '-'])
  })

  it('业务模块换算成模块编码第一段，模块选项随之收窄', () => {
    expect(directoryRoots(['系统管理', 'AI提问'])).toEqual(['auth', 'iam', 'system', 'ai'])
    const codes = [
      'auth', 'system.users', 'policy.sources', 'ai.prompts', 'systemx',
      'codebook.thinktank_file_types', 'thinktank.reports', 'thinktank.proposals', 'thinktank.favorites',
    ]
    expect(modulesInDirectories(codes, ['系统管理'])).toEqual(['auth', 'system.users'])
    expect(modulesInDirectories(codes, ['码表管理'])).toEqual(['codebook.thinktank_file_types'])
    expect(modulesInDirectories(codes, ['智库'])).toEqual(['thinktank.reports', 'thinktank.proposals', 'thinktank.favorites'])
    expect(modulesInDirectories(codes, [])).toEqual(codes)
  })
})
