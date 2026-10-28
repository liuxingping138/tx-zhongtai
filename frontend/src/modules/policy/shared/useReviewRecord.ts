import { computed, reactive, ref, shallowRef, watch, type ShallowRef } from 'vue'
import { onBeforeRouteUpdate, useRoute, useRouter, type LocationQuery } from 'vue-router'
import { ElMessage } from 'element-plus'

import { errorMessage, isApiError } from '@/api/errors'
import type { Page } from '@/api/types'
import type { EditorGroup } from '@/components/editorGroups'
import type { EditorFieldsHandle, RecordForm } from '@/composables/useRecordEditor'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { listQuery, parseReviewQuery, reviewQuery } from './reviewQuery'

export interface ReviewOptions<Row> {
  /** 核对页和列表页的路由名，翻条、返回列表都按名字跳。 */
  routeName: string
  listName: string
  /** 列表的筛选字段，只有它们会从地址栏带进查询。 */
  filterKeys: readonly string[]
  groups: readonly EditorGroup[]
  get: (id: string) => Promise<Row>
  list: (params: Record<string, unknown>) => Promise<Page<Row>>
  /** 由调用方带上版本号等额外字段，和列表页编辑抽屉的保存一致。 */
  update: (row: Row, form: RecordForm) => Promise<Row>
  /** 有没有编辑权限：列表点「编辑」进来（地址栏带 edit=1）时据此直接打开编辑。 */
  canEdit?: () => boolean
}

const STALE_TEXT = '这条记录刚被别人改过，你的修改还在。复制需要保留的内容后点「取消」，会载入最新内容再改。'

/** 地址栏里不影响取哪条记录的参数：只是「打开就编辑」的标记。 */
function withoutEdit(query: LocationQuery): LocationQuery {
  return Object.fromEntries(Object.entries(query).filter(([key]) => key !== 'edit'))
}

function formText(value: unknown): string {
  if (value === null || value === undefined) return ''
  return typeof value === 'string' ? value : JSON.stringify(value)
}

/**
 * 核对页的数据和动作：按地址栏的 ID 取记录，按列表的筛选和位置翻上一条、下一条，
 * 点「编辑」所有分组一起改、一次保存，改了没保存就离开、翻条都要确认。
 */
export function useReviewRecord<Row extends { id: string }>(options: ReviewOptions<Row>) {
  const route = useRoute()
  const router = useRouter()
  const context = computed(() => parseReviewQuery(route.query, options.filterKeys))
  const id = computed(() => String(route.params.id ?? ''))

  const record: ShallowRef<Row | null> = shallowRef(null)
  const loading = ref(false)
  const loadError = ref('')
  const total = ref<number | null>(null)
  const moving = ref(false)
  let ticket = 0

  const pageAt = (position: number) => ({ ...context.value.filters, page: position + 1, page_size: 1 })

  // 整条一起编辑：草稿放所有分组的字段，一次保存。
  const editing = ref(false)
  const draft = reactive<RecordForm>({})
  const saving = ref(false)
  const saveError = ref('')
  const stale = ref(false)
  const fields = ref<EditorFieldsHandle>()
  const guard = useUnsavedForm(editing, () => ({ ...draft }), saving)
  onBeforeRouteUpdate(guard.canLeave)

  async function load() {
    const current = ++ticket
    loading.value = true
    loadError.value = ''
    editing.value = false
    try {
      const position = context.value.position
      const [row, page] = await Promise.all([
        options.get(id.value),
        position === null ? Promise.resolve(null) : options.list(pageAt(position)),
      ])
      if (current !== ticket) return
      record.value = row
      total.value = page ? page.total : null
      await openEditorFromLink()
    } catch (error) {
      if (current !== ticket) return
      record.value = null
      loadError.value = isApiError(error) && error.status === 404
        ? '这条记录不存在或已删除'
        : errorMessage(error, '加载失败，请重试')
    } finally {
      if (current === ticket) loading.value = false
    }
  }
  // 去掉 edit=1 时地址变了但还是同一条，不重新加载，免得刚打开的编辑又被关上。
  const loadKey = computed(() => route.name === options.routeName ? JSON.stringify([id.value, withoutEdit(route.query)]) : '')
  watch(loadKey, (key) => {
    if (key) void load()
  }, { immediate: true })

  const position = computed(() => context.value.position)
  const hasPrev = computed(() => position.value !== null && position.value > 0)
  const hasNext = computed(() => position.value !== null && total.value !== null && position.value + 1 < total.value)

  async function open(row: Row, at: number) {
    await router.replace({
      name: options.routeName,
      params: { id: row.id },
      query: reviewQuery(context.value.filters, at, context.value.pageSize),
    })
  }

  async function move(delta: number) {
    if (position.value === null || moving.value) return
    moving.value = true
    try {
      const target = position.value + delta
      const page = await options.list(pageAt(target))
      total.value = page.total
      const row = page.items[0]
      if (row) await open(row, target)
      else ElMessage.info('筛选结果有变化，这个位置已经没有记录')
    } catch (error) {
      ElMessage.error(errorMessage(error, '没能打开这一条，请重试'))
    } finally {
      moving.value = false
    }
  }

  /**
   * 当前这条处理完（如标为人工验证）后接着看下一条。它若因此出了筛选范围，
   * 后面的记录会补到同一位置上；否则往后挪一条。返回 false 表示已经是最后一条，停在原页。
   */
  async function advance(): Promise<boolean> {
    const at = position.value
    if (at === null) {
      await load()
      return false
    }
    const page = await options.list(pageAt(at))
    total.value = page.total
    const same = page.items[0]
    if (same && same.id !== id.value) {
      await open(same, at)
      return true
    }
    if (at + 1 < page.total) {
      const next = (await options.list(pageAt(at + 1))).items[0]
      if (next) {
        await open(next, at + 1)
        return true
      }
    }
    await load()
    return false
  }

  function backToList() {
    void router.push({ name: options.listName, query: listQuery(context.value) })
  }

  function formOf(row: Row): RecordForm {
    const values = row as Record<string, unknown>
    return Object.fromEntries(options.groups.flatMap(group => group.fields.map(field => [field.key, formText(values[field.key])])))
  }

  function startEdit() {
    if (!record.value || editing.value) return
    for (const key of Object.keys(draft)) delete draft[key]
    Object.assign(draft, formOf(record.value))
    saveError.value = ''
    stale.value = false
    // 先填好草稿再打开：未保存保护在打开的那一刻记下基线。
    editing.value = true
  }

  // 列表点「编辑」进来：先把 edit=1 从地址栏去掉（刷新、翻条不再自动进编辑），有权限再打开。
  async function openEditorFromLink() {
    if (route.query.edit !== '1') return
    await router.replace({ name: options.routeName, params: route.params, query: withoutEdit(route.query) })
    if (options.canEdit?.()) startEdit()
  }

  async function cancelEdit() {
    await guard.close()
    if (!editing.value && stale.value) {
      stale.value = false
      await load()
    }
  }

  async function saveEdit() {
    const row = record.value
    if (!row || saving.value) return
    saveError.value = ''
    if (fields.value && !await fields.value.validate()) return
    saving.value = true
    try {
      record.value = await options.update(row, { ...formOf(row), ...draft })
      guard.markSaved()
      editing.value = false
      ElMessage.success('已保存')
    } catch (error) {
      if (isApiError(error) && error.status === 409) {
        stale.value = true
        saveError.value = STALE_TEXT
      } else {
        saveError.value = errorMessage(error, '保存失败，请检查后重试')
      }
    } finally {
      saving.value = false
    }
  }

  return {
    record,
    loading,
    loadError,
    load,
    total,
    position,
    hasPrev,
    hasNext,
    moving,
    move,
    advance,
    backToList,
    editing,
    draft,
    saving,
    saveError,
    fields,
    dirty: guard.dirty,
    startEdit,
    cancelEdit,
    saveEdit,
  }
}
