import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'

const message = vi.hoisted(() => ({ success: vi.fn() }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: message, ElMessageBox: { confirm: vi.fn() } }))

import { CONFLICT_TEXT, useRecordEditor, type RecordForm } from './useRecordEditor'

interface Row { id: string; version: number; name: string; status?: string }

const groups = [{ title: '基础', hint: '', fields: [{ key: 'name', label: '名称' }, { key: 'status', label: '状态' }] }]

function setup(overrides: Partial<Parameters<typeof useRecordEditor<Row>>[0]> = {}) {
  const create = vi.fn<(form: RecordForm) => Promise<unknown>>().mockResolvedValue({})
  const update = vi.fn<(row: Row, form: RecordForm) => Promise<unknown>>().mockResolvedValue({})
  const refresh = vi.fn<() => Promise<unknown>>().mockResolvedValue(undefined)
  const editor = effectScope().run(() => useRecordEditor<Row>({
    noun: '信源', groups, defaults: { status: '待验证' }, create, update, refresh, ...overrides,
  }))!
  const setError = vi.fn<(key: string, text: string) => Promise<void>>().mockResolvedValue()
  editor.fields.value = { validate: vi.fn<() => Promise<boolean>>().mockResolvedValue(true), setError }
  return { editor, create, update, refresh, setError }
}

describe('useRecordEditor', () => {
  beforeEach(() => message.success.mockReset())

  it('新增时按默认值填表，标题是「新增 + 名称」', () => {
    const { editor } = setup()
    editor.openCreate()
    expect(editor.visible.value).toBe(true)
    expect(editor.title.value).toBe('新增信源')
    expect({ ...editor.form }).toEqual({ name: '', status: '待验证' })
  })

  it('编辑时用记录的值填表，记录里缺的字段才用默认值', () => {
    const { editor } = setup()
    editor.openEdit({ id: '1', version: 3, name: '甲' })
    expect(editor.title.value).toBe('编辑信源')
    expect({ ...editor.form }).toEqual({ name: '甲', status: '待验证' })
  })

  it('编辑保存交给 update 并带上原记录，成功后关闭并刷新', async () => {
    const { editor, update, create, refresh } = setup()
    const row = { id: '1', version: 3, name: '甲', status: '人工验证' }
    editor.openEdit(row)
    editor.form.name = '乙'
    await editor.save()
    expect(update).toHaveBeenCalledWith(row, { name: '乙', status: '人工验证' })
    expect(create).not.toHaveBeenCalled()
    expect(editor.visible.value).toBe(false)
    expect(refresh).toHaveBeenCalledOnce()
    expect(message.success).toHaveBeenCalledOnce()
  })

  it('跨字段规则不通过时把提示落到对应字段上，不发请求', async () => {
    const check = (form: RecordForm) => (form.name ? undefined : { key: 'name', message: '至少填一项' })
    const { editor, create, setError } = setup({ check })
    editor.openCreate()
    await editor.save()
    expect(setError).toHaveBeenCalledWith('name', '至少填一项')
    expect(create).not.toHaveBeenCalled()
  })

  it('版本冲突保留抽屉和草稿，提示刷新核对', async () => {
    const conflict = { status: 409, code: 'VERSION_CONFLICT', message: '版本冲突' }
    const { editor, refresh } = setup({ create: vi.fn().mockRejectedValue(conflict) })
    editor.openCreate()
    editor.form.name = '草稿'
    await editor.save()
    expect(editor.visible.value).toBe(true)
    expect(editor.form.name).toBe('草稿')
    expect(editor.saveError.value).toBe(CONFLICT_TEXT)
    expect(refresh).toHaveBeenCalledOnce()
    expect(editor.saving.value).toBe(false)
  })

  it('其他错误显示服务端的说明', async () => {
    const failure = { status: 422, code: 'VALIDATION_ERROR', message: '网站名称不能为空' }
    const { editor } = setup({ create: vi.fn().mockRejectedValue(failure) })
    editor.openCreate()
    await editor.save()
    expect(editor.saveError.value).toBe('网站名称不能为空')
  })

  it('必填校验没通过时不保存', async () => {
    const { editor, create } = setup()
    editor.fields.value = { validate: vi.fn<() => Promise<boolean>>().mockResolvedValue(false), setError: vi.fn() }
    editor.openCreate()
    await editor.save()
    expect(create).not.toHaveBeenCalled()
  })
})
