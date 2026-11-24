// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { ElOption, ElSelect } from 'element-plus'
import { describe, expect, it } from 'vitest'

import CodebookFilterSelect from './CodebookFilterSelect.vue'

describe('CodebookFilterSelect 码表可搜索单选下拉框', () => {
  it('输入前缀关键词时匹配的码表项排在前面、自定义项排在末尾，精确命中时不重复', async () => {
    const selected: string[] = []
    const wrapper = mount(CodebookFilterSelect, {
      props: {
        modelValue: '',
        options: ['全国', '北京市', '广东省'],
        'onUpdate:modelValue': (val: string) => selected.push(val),
      },
      global: { components: { 'el-select': ElSelect, 'el-option': ElOption } },
    })
    const select = wrapper.findComponent(ElSelect)
    expect(select.props('allowCreate')).toBe(false)

    const filterMethod = select.props('filterMethod') as (q: string) => void
    filterMethod('广东')
    await flushPromises()
    expect(wrapper.findAllComponents(ElOption).map(opt => opt.props('value'))).toEqual(['广东省', '广东'])

    // 精确输入已有候选时不重复追加
    filterMethod('广东省')
    await flushPromises()
    expect(wrapper.findAllComponents(ElOption).map(opt => opt.props('value'))).toEqual(['广东省'])

    // 选中自定义值并收起下拉后，该值仍保留在选项中以免回显空白
    select.vm.$emit('update:modelValue', '  新疆生产建设兵团  ')
    select.vm.$emit('visible-change', false)
    await flushPromises()
    expect(selected).toEqual(['新疆生产建设兵团'])
    await wrapper.setProps({ modelValue: '新疆生产建设兵团' })
    expect(wrapper.findAllComponents(ElOption).map(opt => opt.props('value'))).toEqual([
      '新疆生产建设兵团',
      '全国',
      '北京市',
      '广东省',
    ])
  })

  it('真实键盘输入与中文输入法组合输入：默认回车选码表项，下移方向键可选自定义短词，无匹配时直接创建', async () => {
    const selected: string[] = []
    const wrapper = mount(CodebookFilterSelect, {
      props: {
        modelValue: '',
        options: ['全国', '北京市', '广东省'],
        'onUpdate:modelValue': (val: string) => selected.push(val),
      },
      global: { components: { 'el-select': ElSelect, 'el-option': ElOption } },
    })
    const input = wrapper.find('input')

    // 中文输入法组合期间按回车不误选中，组合结束后按回车默认选中首个码表项「广东省」
    await input.trigger('focus')
    await input.trigger('compositionstart')
    ;(input.element as HTMLInputElement).value = 'guangdong'
    await input.trigger('input')
    await input.trigger('keydown', { code: 'Enter', key: 'Enter' })
    expect(selected).toEqual([])
    ;(input.element as HTMLInputElement).value = '广东'
    await input.trigger('compositionend')
    await flushPromises()
    await input.trigger('keydown', { code: 'Enter', key: 'Enter' })
    await flushPromises()
    expect(selected).toEqual(['广东省'])

    // 确实想选短词「广东」时，按 ArrowDown 下移到末尾自定义项再按回车即可选中
    await input.trigger('focus')
    await input.setValue('广东')
    await flushPromises()
    await input.trigger('keydown', { code: 'ArrowDown', key: 'ArrowDown' })
    await input.trigger('keydown', { code: 'Enter', key: 'Enter' })
    await flushPromises()
    expect(selected).toEqual(['广东省', '广东'])

    // 输入码表不存在的自定义词后直接按回车即可创建
    await input.trigger('focus')
    await input.setValue('新疆生产建设兵团')
    await flushPromises()
    await input.trigger('keydown', { code: 'Enter', key: 'Enter' })
    await flushPromises()
    expect(selected).toEqual(['广东省', '广东', '新疆生产建设兵团'])
  })

  it('码表候选为空（如码表服务暂不可用）时输入自定义词按回车也能直接创建选中', async () => {
    const selected: string[] = []
    const wrapper = mount(CodebookFilterSelect, {
      props: {
        modelValue: '',
        options: [],
        'onUpdate:modelValue': (val: string) => selected.push(val),
      },
      global: { components: { 'el-select': ElSelect, 'el-option': ElOption } },
    })
    const input = wrapper.find('input')
    await input.trigger('focus')
    await input.setValue('新疆生产建设兵团')
    await flushPromises()
    await input.trigger('keydown', { code: 'Enter', key: 'Enter' })
    await flushPromises()
    expect(selected).toEqual(['新疆生产建设兵团'])
  })
})
