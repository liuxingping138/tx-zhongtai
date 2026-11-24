// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { h, type Component } from 'vue'

import type { PromptTemplate } from '@/api/ai'
import { getTaggingSamples, type ContractTask, type TaggingSamples } from '@/api/aiTagging'
import { http } from '@/api/http'
import SampleDialog from './SampleDialog.vue'

vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), error: vi.fn() } }))

const TASKS = [
  { code: 'type', name: '政策类型判断', columns: ['源ID', '政策正文'], required_fields: ['政策类型名称'], optional_fields: [] },
  { code: 'opportunity', name: '政策市场机会', columns: ['源ID', '一级行业', '一级场景'], required_fields: ['市场机会'], optional_fields: [] },
  { code: 'scenario', name: '新增场景找相似', columns: ['源ID', '新增场景'], required_fields: ['判断'], optional_fields: [] },
] as unknown as ContractTask[]

const ElDialog: Component = {
  props: { modelValue: Boolean },
  setup(props, { slots }) {
    return () => (props.modelValue ? h('div', [slots.default?.(), slots.footer?.()]) : null)
  },
}
const ElButton: Component = {
  emits: ['click'],
  setup(_, { slots, emit }) {
    return () => h('button', { onClick: () => emit('click') }, slots.default?.())
  },
}

const TEMPLATE: PromptTemplate = {
  id: 't1',
  title: '测试模板',
  category: 'policy',
  category_name: '政策',
  editable: true,
  content: '',
  output_fields: '政策类型名称',
  fields: ['政策类型名称'],
  model_id: 'm1',
  model_name: '测试模型',
  code_table: '',
  code_table_name: '',
  code_name: '',
  excel_name: '',
  excel_rows: 0,
  excel_headers: [],
  release: null,
  sample: null,
  version: 1,
  created_at: '',
  created_by_name: '',
  updated_at: '',
  updated_by_name: '',
}

describe('SampleDialog 从政策库取测试数据与参数过滤', () => {
  it('按未保存草稿的实时输出字段推断默认任务，走 saveRows 队列，并在切换任务时清空隐藏筛选项', async () => {
    const sample: TaggingSamples = { task: 'opportunity', file_name: '样本.xlsx', headers: ['源ID'], rows: [['c1']], note: '1 条' }
    const getSpy = vi.spyOn(http, 'get').mockResolvedValue(sample)
    const saveRows = vi.fn(() => Promise.resolve({ ...TEMPLATE, excel_name: '样本.xlsx', version: 2 }))

    const wrapper = mount(SampleDialog, {
      props: {
        modelValue: false,
        template: TEMPLATE,
        fields: ['市场机会'],
        tasks: TASKS,
        provinces: ['广东省'],
        industries: ['党政行业'],
        saveRows,
      },
      global: {
        stubs: {
          'el-dialog': ElDialog,
          'el-button': ElButton,
          'el-form': true,
          'el-form-item': true,
          'el-radio-group': true,
          'el-radio': true,
          'el-date-picker': true,
          'el-input-number': true,
          'el-input': true,
          CodebookFilterSelect: true,
        },
        renderStubDefaultSlot: true,
      },
    })

    // 打开弹窗：虽然已存模板 fields 是「政策类型名称」，但当前草稿 fields 为「市场机会」，应默认选中 opportunity
    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    const vm = wrapper.vm as unknown as { task: string; province: string; keyword: string; industryL1: string }
    expect(vm.task).toBe('opportunity')

    vm.province = '广东省'
    vm.keyword = '算力'
    vm.industryL1 = '党政行业'
    const buttons = wrapper.findAll('button')
    await buttons[buttons.length - 1]?.trigger('click')
    await flushPromises()
    expect(getSpy).toHaveBeenLastCalledWith('/policy/ai-tagging/samples', expect.objectContaining({
      params: { task: 'opportunity', limit: 10, province: '广东省', keyword: '算力', industry_l1: '党政行业' },
    }))
    expect(saveRows).toHaveBeenCalledWith({ file_name: '样本.xlsx', headers: ['源ID'], rows: [['c1']] })

    // 切到 scenario（无省份/关键词/行业筛选项）：隐藏筛选项自动清空，请求不再透传脏参数
    vm.task = 'scenario'
    await flushPromises()
    expect([vm.province, vm.keyword, vm.industryL1]).toEqual(['', '', ''])

    // 直接调 getTaggingSamples 传入跨任务残留字段时，API 层也按任务过滤
    await getTaggingSamples('type', '2026-11-23', 5, { province: '广东省', keyword: '算力', industry_l1: '党政行业' })
    expect(getSpy).toHaveBeenLastCalledWith('/policy/ai-tagging/samples', expect.objectContaining({
      params: { task: 'type', day: '2026-11-23', limit: 5, province: '广东省' },
    }))
    getSpy.mockRestore()
  })
})
