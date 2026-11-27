// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { ModuleEntry, ModuleGroup } from '@/permissions/catalog'
import PermissionTable from './PermissionTable.vue'

const entry = (
  code: string,
  name: string,
  levels: ModuleEntry['levels'],
  writes: string[] = [],
  downloadCode?: string,
): ModuleEntry => ({
  code,
  name,
  levels,
  writes,
  ...(downloadCode ? { downloadCode } : {}),
})

const GROUPS: ModuleGroup[] = [
  {
    code: 'policy',
    name: '政策',
    modules: [
      entry('policy.sources', '信源管理', ['NONE', 'READ', 'EXPORT', 'FULL'], ['新增', '编辑']),
      entry('policy.crawler', '爬虫监测', ['NONE', 'READ', 'EXPORT']),
    ],
  },
  {
    code: 'thinktank',
    name: '智库',
    modules: [
      entry('thinktank.knowledge', '资料库', ['NONE', 'READ', 'EXPORT', 'FULL'], ['上传文件'], 'thinktank.knowledge.download'),
    ],
  },
]

const STUBS = {
  ElIcon: { template: '<span class="el-icon"><slot /></span>' },
  ElTooltip: { template: '<span><slot /></span>' },
  ElInput: {
    props: ['modelValue', 'placeholder'],
    emits: ['update:modelValue'],
    template: '<input :value="modelValue" :placeholder="placeholder" aria-label="搜索菜单" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
}

describe('PermissionTable', () => {
  it('supports sticky header crosshair highlight, status filtering, group collapse, and scope jump', async () => {
    const wrapper = mount(PermissionTable, {
      props: {
        groups: GROUPS,
        modelValue: { 'policy.sources': 'FULL', 'thinktank.knowledge': 'EXPORT' },
        original: { 'policy.sources': 'READ', 'thinktank.knowledge': 'EXPORT' },
        disabled: false,
        scopeBadges: { 'thinktank.knowledge': '范围：文件 10/16 · 行业 8/12' },
      },
      global: { stubs: STUBS },
    })

    // 吸顶列头带副标题，鼠标悬停单元格时触发十字列高亮
    expect(wrapper.find('.perm-thead').text()).toContain('列表/详情')
    const firstCell = wrapper.find('.perm-table__row .perm-cell')
    await firstCell.trigger('mouseenter')
    expect(wrapper.findAll('.perm-th--col')[0]?.classes()).toContain('is-col-hover')
    await firstCell.trigger('mouseleave')
    expect(wrapper.findAll('.perm-th--col')[0]?.classes()).not.toContain('is-col-hover')

    // 左侧生效档位小标签与「已修改」标识
    expect(wrapper.text()).toContain('可管理')
    expect(wrapper.text()).toContain('已修改')

    // 点击资料库数据范围徽章抛出 openScope 事件
    await wrapper.find('.perm-scope-chip').trigger('click')
    expect(wrapper.emitted('openScope')?.[0]).toEqual(['thinktank.knowledge'])

    // 按状态筛选：仅看已修改只保留信源管理
    const changedBtn = wrapper.findAll('.perm-filter-chip').find(b => b.text().includes('已修改'))!
    await changedBtn.trigger('click')
    expect(wrapper.findAll('.perm-table__row')).toHaveLength(1)
    expect(wrapper.find('.perm-table__row').text()).toContain('信源管理')

    // 切回全部并测试分组折叠与一键收起
    await wrapper.findAll('.perm-filter-chip')[0]!.trigger('click')
    expect(wrapper.findAll('.perm-table__row')).toHaveLength(3)
    await wrapper.find('.perm-collapse-btn').trigger('click')
    expect(wrapper.findAll('.perm-table__row')).toHaveLength(0)
    await wrapper.find('.perm-collapse-btn').trigger('click')
    expect(wrapper.findAll('.perm-table__row')).toHaveLength(3)

    // 勾选单元格发出更新事件；下载列仅对智库展示，爬虫监测保持 2 个复选框
    const crawlerRow = wrapper.findAll('.perm-table__row').find(r => r.text().includes('爬虫监测'))!
    expect(crawlerRow.findAll('input[type="checkbox"]')).toHaveLength(2)
    const crawlerRead = wrapper.find('input[aria-label="爬虫监测 查看"]')
    await crawlerRead.trigger('change')
    const dlCheck = wrapper.find('input[aria-label="资料库 下载"]')
    await dlCheck.trigger('change')
    const updates = wrapper.emitted('update:modelValue')
    expect(updates?.[0]?.[0]).toMatchObject({ 'policy.crawler': 'READ' })
    expect(updates?.[1]?.[0]).toMatchObject({
      'thinktank.knowledge': 'EXPORT',
      'thinktank.knowledge.download': 'READ',
    })
  })
})
