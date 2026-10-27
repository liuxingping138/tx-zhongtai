import { computed, reactive, ref, shallowRef, watch, type ShallowRef } from 'vue'
import { onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
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
}

const STALE_TEXT = '这条记录刚被别人改过，你的修改还在。复制需要保留的内容后点「取消」，会载入最新内容再改。'

function formText(value: unknown): string {
  if (value === null || value === undefined) return ''
  return typeof value === 'string' ? value : JSON.stringify(value)
}

/**
 * 核对页的数据和动作：按地址栏的 ID 取记录，按列表的筛选和位置翻上一条、下一条，
 * 一次只编辑一组字段，改了没保存就离开、翻条都要确认。
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

  // 按组编辑：editing 是正在改的组名，草稿只放这一组的字段。
  const editing = ref<string | null>(null)
  const editorOpen = ref(false)
  const draft = reactive<RecordForm>({})
  const saving = ref(false)
  const saveError = ref('')
  const stale = ref(false)
  const fields = ref<EditorFieldsHandle>()
  const guard = useUnsavedForm(editorOpen, () => ({ ...draft }), saving)
  watch(editorOpen, (open) => {
    if (!open) editing.value = null
  })
  onBeforeRouteUpdate(guard.canLeave)

  async function load() {
    const current = ++ticket
    loading.value = true
    loadError.value = ''
    editorOpen.value = false
    try {
      const position = context.value.position
      const [row, page] = await Promise.all([
        options.get(id.value),
        position === null ? Promise.resolve(null) : options.list(pageAt(position)),
      ])
      if (current !== ticket) return
      record.value = row
      total.value = page ? page.total : null
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
  watch(() => route.fullPath, () => {
    if (route.name === options.routeName) void load()
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

  async function startEdit(title: string) {
    const group = options.groups.find(item => item.title === title)
    if (!group || !record.value || !await guard.canLeave()) return
    for (const key of Object.keys(draft)) delete draft[key]
    const values = record.value as Record<string, unknown>
    for (const field of group.fields) draft[field.key] = formText(values[field.key])
    saveError.value = ''
    stale.value = false
    editorOpen.value = false
    editing.value = title
    // 先填好草稿再打开：未保存保护在打开的那一刻记下基线。
    editorOpen.value = true
  }

  async function cancelEdit() {
    await guard.close()
    if (!editorOpen.value && stale.value) {
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
      editorOpen.value = false
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
