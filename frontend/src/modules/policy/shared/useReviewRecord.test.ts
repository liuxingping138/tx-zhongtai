import { afterEach, describe, expect, it, vi, type Mock } from 'vitest'
import { effectScope, nextTick, reactive } from 'vue'

const state = vi.hoisted((): { route: unknown; replace: Mock; push: Mock } => ({ route: null, replace: vi.fn(), push: vi.fn() }))
const message = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))
vi.mock('vue-router', () => ({
  useRoute: () => state.route,
  useRouter: () => ({ replace: state.replace, push: state.push }),
  onBeforeRouteUpdate: vi.fn(),
  onBeforeRouteLeave: vi.fn(),
}))
vi.mock('element-plus', () => ({ ElMessage: message, ElMessageBox: { confirm: vi.fn() } }))

import { ApiRequestError } from '@/api/errors'
import type { Page } from '@/api/types'
import { useReviewRecord } from './useReviewRecord'

interface Row { id: string; title: string; note: string; version: number }

const groups = [
  { title: '基本信息', hint: '', fields: [{ key: 'title', label: '标题' }] },
  { title: '解读内容', hint: '', fields: [{ key: 'note', label: '备注', long: true }] },
]
const flush = () => new Promise(resolve => setTimeout(resolve, 0))
const apiError = (status: number, code: string, text: string) => new ApiRequestError({ status, code, message: text, requestId: null })
const fieldsHandle = (valid: boolean) => ({ validate: vi.fn(() => Promise.resolve(valid)), setError: vi.fn(() => Promise.resolve()) })
const scopes: ReturnType<typeof effectScope>[] = []
afterEach(() => {
  scopes.forEach(scope => scope.stop())
  scopes.length = 0
  vi.clearAllMocks()
})

function setup(id: string, query: Record<string, string | string[]> = {}, initial?: Row[], canEdit = true) {
  const rows: Row[] = initial ?? [
    { id: 'a', title: '甲', note: '一', version: 1 },
    { id: 'b', title: '乙', note: '二', version: 1 },
    { id: 'c', title: '丙', note: '三', version: 1 },
  ]
  const route = reactive({ name: 'review', params: { id }, query, fullPath: `/review/${id}` })
  state.route = route
  state.replace.mockImplementation(async (target: { params: { id: string }; query: Record<string, string> }) => {
    route.params = target.params
    route.query = target.query
    route.fullPath = `/review/${target.params.id}?pos=${target.query.pos}`
    await nextTick()
  })
  const get = vi.fn((key: string) => {
    const row = rows.find(item => item.id === key)
    return row ? Promise.resolve({ ...row }) : Promise.reject(apiError(404, 'RESOURCE_NOT_FOUND', '不存在'))
  })
  const list = vi.fn((params: Record<string, unknown>): Promise<Page<Row>> => {
    const at = Number(params.page) - 1
    return Promise.resolve({ items: rows.slice(at, at + 1), total: rows.length, page: at + 1, page_size: 1 })
  })
  const update = vi.fn((row: Row, form: Record<string, string>) => Promise.resolve({ ...row, ...form, version: row.version + 1 }))
  const scope = effectScope()
  scopes.push(scope)
  const review = scope.run(() => useReviewRecord<Row>({
    routeName: 'review', listName: 'list', filterKeys: ['status'], groups, get, list, update, canEdit: () => canEdit,
  }))!
  review.fields.value = fieldsHandle(true)
  return { review, route, rows, get, list, update }
}

describe('opening a record', () => {
  it('loads the record and the size of the filtered list it came from', async () => {
    const { review, list } = setup('b', { status: '待验证', pos: '1' })
    await flush()
    expect(review.record.value?.title).toBe('乙')
    expect(review.total.value).toBe(3)
    expect(list).toHaveBeenCalledWith({ status: ['待验证'], page: 2, page_size: 1 })
    expect(review.hasPrev.value).toBe(true)
    expect(review.hasNext.value).toBe(true)
  })

  it('opened from a bare link has no previous and next', async () => {
    const { review, list } = setup('a')
    await flush()
    expect(review.record.value?.title).toBe('甲')
    expect(list).not.toHaveBeenCalled()
    expect(review.hasPrev.value).toBe(false)
    expect(review.hasNext.value).toBe(false)
  })

  it('says the record is gone instead of a generic failure', async () => {
    const { review } = setup('missing')
    await flush()
    expect(review.record.value).toBeNull()
    expect(review.loadError.value).toBe('这条记录不存在或已删除')
  })

  it('reports other failures with the server message', async () => {
    const { review, get } = setup('a')
    await flush()
    get.mockRejectedValueOnce(apiError(503, 'UNAVAILABLE', '源库连不上'))
    await review.load()
    expect(review.loadError.value).toBe('源库连不上')
  })
})

describe('moving through the list', () => {
  it('opens the next record at the next position, keeping the filters', async () => {
    const { review, route } = setup('a', { status: '待验证', pos: '0' })
    await flush()
    await review.move(1)
    await flush()
    expect(state.replace).toHaveBeenCalledWith({ name: 'review', params: { id: 'b' }, query: { status: ['待验证'], pos: '1' } })
    expect(route.params.id).toBe('b')
    expect(review.record.value?.title).toBe('乙')
    expect(review.hasNext.value).toBe(true)
  })

  it('tells the user when the list changed and the position is empty', async () => {
    const { review, rows } = setup('c', { pos: '2' })
    await flush()
    rows.splice(2, 1)
    await review.move(1)
    expect(message.info).toHaveBeenCalled()
    expect(state.replace).not.toHaveBeenCalled()
  })

  it('after handling a record that left the filter, opens the one that took its place', async () => {
    const { review, rows } = setup('a', { pos: '0' })
    await flush()
    rows.shift()
    expect(await review.advance()).toBe(true)
    expect(state.replace).toHaveBeenCalledWith(expect.objectContaining({ params: { id: 'b' }, query: { pos: '0' } }))
  })

  it('otherwise moves on to the next position, and stays on the last one', async () => {
    const { review } = setup('b', { pos: '1' })
    await flush()
    expect(await review.advance()).toBe(true)
    expect(state.replace).toHaveBeenCalledWith(expect.objectContaining({ params: { id: 'c' }, query: { pos: '2' } }))
    await flush()
    state.replace.mockClear()
    expect(await review.advance()).toBe(false)
    expect(state.replace).not.toHaveBeenCalled()
  })

  it('returns to the list page that holds the record', async () => {
    const { review } = setup('c', { status: '待验证', pos: '45', ps: '20' })
    await flush()
    review.backToList()
    expect(state.push).toHaveBeenCalledWith({ name: 'list', query: { status: ['待验证'], page: '3' } })
  })
})

describe('editing the record', () => {
  it('fills every group and saves them together', async () => {
    const { review, update } = setup('a')
    await flush()
    review.startEdit()
    expect(review.editing.value).toBe(true)
    expect({ ...review.draft }).toEqual({ title: '甲', note: '一' })
    review.draft.note = '改过'
    expect(review.dirty.value).toBe(true)
    await review.saveEdit()
    expect(update).toHaveBeenCalledWith(expect.objectContaining({ id: 'a' }), { title: '甲', note: '改过' })
    expect(review.record.value).toMatchObject({ note: '改过', version: 2 })
    await nextTick()
    expect(review.editing.value).toBe(false)
    expect(message.success).toHaveBeenCalledWith('已保存')
  })

  it('cannot edit while the next record is still loading, so the previous one is never saved over it', async () => {
    const { review, get, update } = setup('a', { pos: '0' })
    await flush()
    let release: () => void = () => undefined
    get.mockImplementationOnce((key: string) => new Promise(resolve => {
      release = () => resolve({ id: key, title: '乙', note: '二', version: 1 })
    }))
    void review.move(1)
    await flush()
    // 地址已经是下一条，页面上还是上一条：这时不能编辑。
    expect(review.record.value?.id).toBe('a')
    expect(review.ready.value).toBe(false)
    review.startEdit()
    expect(review.editing.value).toBe(false)
    release()
    await flush()
    expect(review.ready.value).toBe(true)
    review.startEdit()
    expect({ ...review.draft }).toEqual({ title: '乙', note: '二' })
    await review.saveEdit()
    expect(update).toHaveBeenCalledWith(expect.objectContaining({ id: 'b' }), { title: '乙', note: '二' })
  })

  it('does not save when a required field is empty', async () => {
    const { review, update } = setup('a')
    await flush()
    review.startEdit()
    review.fields.value = fieldsHandle(false)
    await review.saveEdit()
    expect(update).not.toHaveBeenCalled()
  })

  it('keeps the draft on a conflict and reloads the latest record after cancelling', async () => {
    const { review, update, get } = setup('a')
    await flush()
    review.startEdit()
    review.draft.note = '我的修改'
    update.mockRejectedValueOnce(apiError(409, 'VERSION_CONFLICT', '版本冲突'))
    await review.saveEdit()
    expect(review.saveError.value).toContain('刚被别人改过')
    expect(review.draft.note).toBe('我的修改')
    get.mockClear()
    review.draft.note = '一'
    await review.cancelEdit()
    expect(get).toHaveBeenCalledWith('a')
  })

  it('shows the server reason for other save failures', async () => {
    const { review, update } = setup('a')
    await flush()
    review.startEdit()
    update.mockRejectedValueOnce(apiError(422, 'VALIDATION_FAILED', '备注超过长度'))
    await review.saveEdit()
    expect(review.saveError.value).toBe('备注超过长度')
  })

  it('opens the editor when the list\'s edit link asks for it, without reloading the record', async () => {
    const { review, get } = setup('a', { pos: '0', edit: '1' })
    await flush()
    expect(state.replace).toHaveBeenCalledWith({ name: 'review', params: { id: 'a' }, query: { pos: '0' } })
    expect(review.editing.value).toBe(true)
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('does not open the editor from a link for someone who cannot edit', async () => {
    const { review } = setup('a', { edit: '1' }, undefined, false)
    await flush()
    expect(review.editing.value).toBe(false)
  })
})
