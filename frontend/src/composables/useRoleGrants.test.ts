import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getRole: vi.fn<(id: string) => Promise<unknown>>(),
  listResourceTree: vi.fn<() => Promise<unknown>>(),
  listRoleGrants: vi.fn<(id: string) => Promise<unknown>>(),
  replaceRoleGrants: vi.fn<(id: string, body: unknown) => Promise<unknown>>(),
}))
const ui = vi.hoisted(() => ({
  confirm: vi.fn<(message: string, title: string) => Promise<unknown>>(),
  alert: vi.fn<() => Promise<unknown>>(),
  success: vi.fn(),
  error: vi.fn(),
}))
vi.mock('@/api/system', () => api)
vi.mock('element-plus', () => ({
  ElMessage: { success: ui.success, error: ui.error },
  ElMessageBox: { confirm: ui.confirm, alert: ui.alert },
}))

import { wasShown } from '@/api/errors'
import type { ResourceNode } from '@/api/types'
import { collectGrants, useRoleGrants } from './useRoleGrants'

const node = (code: string, extra: Partial<ResourceNode> = {}) => ({
  id: code, code, name: code, service_code: 'x', node_type: 'resource', published: true, sort_order: 1,
  parent_id: null, actions: [{ action_code: 'list', required_level: 'READ' }, { action_code: 'update', required_level: 'FULL' }],
  children: [], ...extra,
}) as unknown as ResourceNode
const directory = node('policy', { node_type: 'directory', children: [node('policy.sources'), node('policy.draft', { published: false })] })
const TREE = [directory]
const ROLE = { id: 'r1', name: '编辑', code: 'editor', version: 3, is_builtin: false }

function setup(overrides: { readonly?: boolean; see?: boolean; created?: string } = {}) {
  const saved = vi.fn()
  const grants = useRoleGrants({
    roleId: () => 'r1',
    canSeeGrants: () => overrides.see ?? true,
    readonly: () => overrides.readonly ?? false,
    justCreated: () => overrides.created ?? '',
    saved,
  })
  return { grants, saved }
}

beforeEach(() => {
  Object.values(api).forEach(fn => fn.mockReset())
  ui.confirm.mockReset().mockResolvedValue('confirm')
  ui.alert.mockReset().mockResolvedValue('confirm')
  ui.success.mockReset()
  ui.error.mockReset()
  api.getRole.mockResolvedValue(ROLE)
  api.listResourceTree.mockResolvedValue({ tree: TREE })
  api.listRoleGrants.mockResolvedValue({ role: ROLE, grants: [{ resource_code: 'policy.sources', level: 'READ' }] })
})

describe('collectGrants', () => {
  it('只收集已发布的资源节点，目录和草稿不进去，缺失的按无权限', () => {
    expect(collectGrants(TREE, { 'policy.sources': 'FULL' })).toEqual({ 'policy.sources': 'FULL' })
    expect(collectGrants(TREE, {})).toEqual({ 'policy.sources': 'NONE' })
  })
})

describe('load', () => {
  it('加载角色、资源树和已有授权，草稿与已保存值一致', async () => {
    const { grants } = setup()
    await grants.load()
    expect(grants.role.value?.name).toBe('编辑')
    expect(grants.selected.value).toEqual({ 'policy.sources': 'READ' })
    expect(grants.changes.value).toEqual([])
    expect(grants.openedCount.value).toBe(1)
  })

  it('已有资源树时再次加载不重复请求', async () => {
    const { grants } = setup()
    await grants.load()
    await grants.load()
    expect(api.listResourceTree).toHaveBeenCalledOnce()
  })

  it('没有查看授权的权限时只加载角色', async () => {
    const { grants } = setup({ see: false })
    await grants.load()
    expect(api.listRoleGrants).not.toHaveBeenCalled()
    expect(grants.role.value?.code).toBe('editor')
    expect(grants.selected.value).toEqual({})
  })

  it('快速切换角色时先发的请求后回来，不盖掉后一个角色', async () => {
    let roleId = 'a'
    const grants = useRoleGrants({ roleId: () => roleId, canSeeGrants: () => true, readonly: () => false, justCreated: () => '', saved: vi.fn() })
    let releaseA!: (value: unknown) => void
    api.getRole.mockImplementation((id: string) => (id === 'a'
      ? new Promise((resolve) => { releaseA = resolve })
      : Promise.resolve({ ...ROLE, id: 'b', name: '角色B' })))
    const first = grants.load()
    roleId = 'b'
    await grants.load()
    releaseA({ ...ROLE, id: 'a', name: '角色A' })
    await first
    expect(grants.role.value?.name).toBe('角色B')
    expect(grants.loading.value).toBe(false)
  })

  it('加载失败显示原因', async () => {
    api.getRole.mockRejectedValue({ status: 404, code: 'NOT_FOUND', message: '角色不存在' })
    const { grants } = setup()
    await grants.load()
    expect(grants.loadError.value).toBe('角色不存在')
    expect(grants.loading.value).toBe(false)
  })
})

describe('save', () => {
  async function edited(options: Parameters<typeof setup>[0] = {}) {
    const ctx = setup(options)
    await ctx.grants.load()
    ctx.grants.selected.value = { 'policy.sources': 'FULL' }
    return ctx
  }

  it('没有修改或只读时什么都不做', async () => {
    const { grants } = setup()
    await grants.load()
    await grants.save()
    const readonly = await edited({ readonly: true })
    await readonly.grants.save()
    expect(ui.confirm).not.toHaveBeenCalled()
    expect(api.replaceRoleGrants).not.toHaveBeenCalled()
  })

  it('确认框里逐项写出「模块：旧档 → 新档」，取消则不提交也不卡住保存状态', async () => {
    ui.confirm.mockRejectedValue('cancel')
    const { grants } = await edited()
    await grants.save()
    expect(ui.confirm.mock.calls[0]?.[0]).toContain('policy.sources')
    expect(ui.confirm.mock.calls[0]?.[0]).toContain('→')
    expect(api.replaceRoleGrants).not.toHaveBeenCalled()
    expect(grants.saving.value).toBe(false)
  })

  it('保存成功带上角色版本号，已保存值更新，并通知列表刷新', async () => {
    api.replaceRoleGrants.mockResolvedValue({ role: { ...ROLE, version: 4 }, grants: [] })
    const { grants, saved } = await edited()
    await grants.save()
    expect(api.replaceRoleGrants).toHaveBeenCalledWith('r1', {
      version: 3,
      grants: [{ resource_code: 'policy.sources', level: 'FULL' }],
    })
    expect(grants.changes.value).toEqual([])
    expect(saved).toHaveBeenCalledOnce()
    expect(ui.success).toHaveBeenCalledWith('权限已保存，成员下次操作时即生效')
  })

  it('刚新建的角色保存后提示去分配成员', async () => {
    api.replaceRoleGrants.mockResolvedValue({ role: ROLE, grants: [] })
    const { grants } = await edited({ created: 'new' })
    await grants.save()
    expect(ui.success.mock.calls[0]?.[0]).toContain('成员')
  })

  it('版本冲突时提示并重新加载最新授权，不覆盖对方的修改，并标记为已展示', async () => {
    const conflict = { status: 409, code: 'VERSION_CONFLICT', message: '冲突' }
    api.replaceRoleGrants.mockRejectedValue(conflict)
    const { grants } = await edited()
    api.listRoleGrants.mockResolvedValue({ role: ROLE, grants: [{ resource_code: 'policy.sources', level: 'EXPORT' }] })
    await grants.save()
    expect(wasShown(conflict)).toBe(true)
    expect(ui.alert).toHaveBeenCalledOnce()
    expect(grants.selected.value).toEqual({ 'policy.sources': 'EXPORT' })
    expect(grants.saving.value).toBe(false)
  })

  it('409 重复错误（DUPLICATE）走普通错误提示而非版本冲突弹窗', async () => {
    const duplicate = { status: 409, code: 'DUPLICATE', message: '授权重复' }
    api.replaceRoleGrants.mockRejectedValue(duplicate)
    const { grants } = await edited()
    await grants.save()
    expect(wasShown(duplicate)).toBe(true)
    expect(ui.alert).not.toHaveBeenCalled()
    expect(ui.error).toHaveBeenCalledWith('授权重复')
  })

  it('其他错误只提示', async () => {
    api.replaceRoleGrants.mockRejectedValue({ status: 500, code: 'X', message: '服务繁忙' })
    const { grants } = await edited()
    await grants.save()
    expect(ui.error).toHaveBeenCalledWith('服务繁忙')
  })
})

describe('reset 与 confirmDiscard', () => {
  it('重置回已保存的值', async () => {
    const { grants } = setup()
    await grants.load()
    grants.selected.value = { 'policy.sources': 'FULL' }
    grants.reset()
    expect(grants.changes.value).toEqual([])
  })

  it('没有未保存修改时离开不弹框，有修改时按用户选择', async () => {
    const { grants } = setup()
    await grants.load()
    expect(await grants.confirmDiscard('离开')).toBe(true)
    expect(ui.confirm).not.toHaveBeenCalled()
    grants.selected.value = { 'policy.sources': 'FULL' }
    ui.confirm.mockRejectedValueOnce('cancel')
    expect(await grants.confirmDiscard('离开')).toBe(false)
    expect(await grants.confirmDiscard('离开')).toBe(true)
  })
})
