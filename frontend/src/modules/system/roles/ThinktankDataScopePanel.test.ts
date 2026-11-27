// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { ThinktankLibraryScope } from '@/permissions/thinktankScopes'
import ThinktankDataScopePanel from './ThinktankDataScopePanel.vue'

const LIBRARIES: ThinktankLibraryScope[] = [
  {
    code: 'thinktank.knowledge',
    name: '资料库',
    dimensions: [
      {
        code: 'thinktank.knowledge.file_type',
        name: '文件类型范围',
        modules: [
          { code: 'thinktank.file_type.product', name: '产品', levels: ['NONE', 'READ', 'EXPORT', 'FULL'], writes: ['编辑'] },
          { code: 'thinktank.file_type.notice', name: '通知', levels: ['NONE', 'READ', 'EXPORT', 'FULL'], writes: ['编辑'] },
        ],
      },
    ],
  },
]

const STUBS = {
  ElIcon: { template: '<span class="el-icon"><slot /></span>' },
  ElButton: {
    props: ['disabled'],
    template: '<button type="button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
  ElInput: {
    props: ['modelValue', 'placeholder'],
    emits: ['update:modelValue'],
    template: '<input :value="modelValue" :placeholder="placeholder" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
}

describe('ThinktankDataScopePanel', () => {
  it('quick-opens library when closed and syncs scope dimensions', async () => {
    const wrapper = mount(ThinktankDataScopePanel, {
      props: {
        libraries: LIBRARIES,
        modelValue: { 'thinktank.knowledge': 'NONE' },
        original: { 'thinktank.knowledge': 'NONE' },
        disabled: false,
      },
      global: { stubs: STUBS },
    })

    expect(wrapper.text()).toContain('尚未开通「资料库」菜单访问权限')
    const btn = wrapper.findAll('button').find(b => b.text().includes('可管理'))!
    await btn.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]?.[0]).toMatchObject({
      'thinktank.knowledge': 'FULL',
      'thinktank.file_type.product': 'FULL',
      'thinktank.file_type.notice': 'FULL',
    })
  })

  it('switches to custom card grid, respects menu cap, filters, and supports batch actions', async () => {
    const wrapper = mount(ThinktankDataScopePanel, {
      props: {
        libraries: LIBRARIES,
        modelValue: {
          'thinktank.knowledge': 'EXPORT',
          'thinktank.file_type.product': 'EXPORT',
          'thinktank.file_type.notice': 'READ',
        },
        original: {
          'thinktank.knowledge': 'EXPORT',
          'thinktank.file_type.product': 'EXPORT',
          'thinktank.file_type.notice': 'EXPORT',
        },
        disabled: false,
      },
      global: { stubs: STUBS },
    })

    // 自定义状态下直接呈现分级卡片网格，且高于菜单档位（EXPORT）的「管」按钮被禁用
    expect(wrapper.findAll('.tt-item-card')).toHaveLength(2)
    const fullBtn = wrapper.find('button[aria-label="产品 可管理"]')
    expect((fullBtn.element as HTMLButtonElement).disabled).toBe(true)

    // 单项切换档位
    await wrapper.find('button[aria-label="产品 仅查看"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]?.[0]).toMatchObject({
      'thinktank.file_type.product': 'READ',
    })

    // 维度专属搜索与「仅看已修改」筛选
    await wrapper.find('.tt-dim-search').setValue('通知')
    expect(wrapper.findAll('.tt-item-card')).toHaveLength(1)
    await wrapper.find('.tt-dim-search').setValue('')
    await wrapper.find('.tt-dirty-toggle').trigger('click')
    expect(wrapper.findAll('.tt-item-card')).toHaveLength(1)
    expect(wrapper.find('.tt-item-card').text()).toContain('通知')

    // 批量清空按钮
    const clearAllBtn = wrapper.findAll('.tt-batch-btn').find(b => b.text() === '全部清空')!
    await clearAllBtn.trigger('click')
    const lastPayload = wrapper.emitted('update:modelValue')?.at(-1)?.[0]
    expect(lastPayload).toMatchObject({
      'thinktank.file_type.product': 'NONE',
      'thinktank.file_type.notice': 'NONE',
    })
  })
})
