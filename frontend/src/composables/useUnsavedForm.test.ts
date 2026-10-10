import { describe, expect, it, vi } from 'vitest'
import { effectScope, reactive, ref } from 'vue'

vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessageBox: { confirm: vi.fn() } }))

import { useUnsavedForm } from './useUnsavedForm'

function setup() {
  const visible = ref(false)
  const form = reactive({ name: '' })
  const scope = effectScope()
  const guard = scope.run(() => useUnsavedForm(visible, () => ({ ...form }), ref(false)))!
  return { visible, form, guard }
}

describe('useUnsavedForm', () => {
  it('打开时以当时的内容为基线，改动后才算未保存', () => {
    const { visible, form, guard } = setup()
    visible.value = true
    expect(guard.dirty.value).toBe(false)
    form.name = '张三'
    expect(guard.dirty.value).toBe(true)
  })

  it('打开后才清空上次残留的内容时，要 markSaved 重新定基线，否则一打开就提示未保存', () => {
    const { visible, form, guard } = setup()
    form.name = '上次没提交的'
    visible.value = true
    form.name = ''
    expect(guard.dirty.value).toBe(true)
    guard.markSaved()
    expect(guard.dirty.value).toBe(false)
  })

  it('保存后的值与表单相同（表单没有触发变化）时，markSaved 也要立刻清掉未保存提示', () => {
    const { visible, form, guard } = setup()
    visible.value = true
    form.name = '张三'
    expect(guard.dirty.value).toBe(true)
    guard.markSaved()
    expect(guard.dirty.value).toBe(false)
  })

  it('关闭状态下不算未保存', () => {
    const { form, guard } = setup()
    form.name = '张三'
    expect(guard.dirty.value).toBe(false)
  })
})
