import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, reactive, ref } from 'vue'

const confirm = vi.hoisted(() => vi.fn<() => Promise<unknown>>())
const routeLeave = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({ onBeforeRouteLeave: routeLeave }))
vi.mock('element-plus', () => ({ ElMessageBox: { confirm } }))

import { useUnsavedForm } from './useUnsavedForm'

function setup() {
  const visible = ref(false)
  const saving = ref(false)
  const form = reactive({ name: '' })
  const scope = effectScope()
  const guard = scope.run(() => useUnsavedForm(visible, () => ({ ...form }), saving))!
  return { visible, saving, form, guard }
}

function setupEdited() {
  const state = setup()
  state.visible.value = true
  state.form.name = '张三'
  return state
}

describe('useUnsavedForm', () => {
  beforeEach(() => {
    confirm.mockReset()
    routeLeave.mockReset()
  })

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
    const { guard } = setupEdited()
    expect(guard.dirty.value).toBe(true)
    guard.markSaved()
    expect(guard.dirty.value).toBe(false)
  })

  it('关闭状态下不算未保存', () => {
    const { form, guard } = setup()
    form.name = '张三'
    expect(guard.dirty.value).toBe(false)
  })

  it('没改过直接关闭，不弹确认', async () => {
    const { visible, guard } = setup()
    visible.value = true
    await guard.close()
    expect(visible.value).toBe(false)
    expect(confirm).not.toHaveBeenCalled()
  })

  it('改过之后关闭要确认，选「继续编辑」就留在原处，选「放弃修改」才关', async () => {
    const { visible, guard } = setupEdited()
    confirm.mockRejectedValueOnce('cancel')
    await guard.close()
    expect(visible.value).toBe(true)

    confirm.mockResolvedValueOnce('confirm')
    const done = vi.fn()
    await guard.beforeClose(done)
    expect(done).toHaveBeenCalled()
  })

  it('连续触发离开只弹一次确认框', async () => {
    const { guard } = setupEdited()
    confirm.mockResolvedValueOnce('confirm')
    expect(await Promise.all([guard.canLeave(), guard.canLeave()])).toEqual([true, true])
    expect(confirm).toHaveBeenCalledTimes(1)
  })

  it('保存中不允许离开', async () => {
    const { visible, saving, guard } = setup()
    visible.value = true
    saving.value = true
    expect(await guard.canLeave()).toBe(false)
  })

  it('路由离开走同一套确认', () => {
    setup()
    expect(routeLeave).toHaveBeenCalledTimes(1)
  })
})
