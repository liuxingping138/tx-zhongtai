import { computed, reactive, ref, shallowRef, type ComputedRef, type Ref, type ShallowRef } from 'vue'
import { ElMessage } from 'element-plus'

import { errorMessage, isStaleConflict } from '@/api/errors'
import type { EditorGroup } from '@/components/editorGroups'
import { useUnsavedForm } from './useUnsavedForm'

export type RecordForm = Record<string, string>

/** 落在某个字段上的校验提示。 */
export interface FieldError {
  key: string
  message: string
}

/** 抽屉里 GroupedFields 暴露的校验能力。 */
export interface EditorFieldsHandle {
  validate: () => Promise<boolean>
  setError: (key: string, message: string) => Promise<void>
}

interface RecordEditorOptions<Row> {
  /** 记录的名称，用在抽屉标题「新增信源 / 编辑信源」里。 */
  noun: string
  groups: EditorGroup[]
  /** 新增时的预填值；编辑时记录里没有的字段也用它补。 */
  defaults?: RecordForm
  create: (form: RecordForm) => Promise<unknown>
  /** 由调用方带上版本号等额外字段，后端靠版本号发现并发修改。 */
  update: (row: Row, form: RecordForm) => Promise<unknown>
  /** 必填之外的跨字段规则（如「省市区编码至少填一项」）。 */
  check?: (form: RecordForm) => FieldError | undefined
  /** 保存成功或遇到冲突后刷新列表和筛选项。 */
  refresh: () => Promise<unknown>
}

/** 编辑抽屉用到的状态和动作，RecordEditorDrawer 只依赖这部分，与记录类型无关。 */
export interface RecordEditorView {
  visible: Ref<boolean>
  saving: Ref<boolean>
  saveError: Ref<string>
  title: ComputedRef<string>
  form: RecordForm
  fields: Ref<EditorFieldsHandle | undefined>
  guard: ReturnType<typeof useUnsavedForm>
  save: () => Promise<void>
}

/** 记录里的字段值转成表单文本；没有值时返回 undefined，由默认值补上。 */
function fieldText(value: unknown): string | undefined {
  if (value === null || value === undefined) return undefined
  return typeof value === 'string' ? value : JSON.stringify(value)
}

export const CONFLICT_TEXT = '数据已被他人修改。请保留需要的内容，关闭后重新打开最新记录再修改。'

/**
 * 业务表的新增与编辑：打开时填表、保存前校验、冲突时保留草稿并提示。
 * 一个列表页一个实例，抽屉组件和列表行的「编辑」共用。
 */
export function useRecordEditor<Row extends object>(options: RecordEditorOptions<Row>) {
  const keys = options.groups.flatMap(group => group.fields.map(field => field.key))
  const visible = ref(false)
  const saving = ref(false)
  const saveError = ref('')
  const editing: ShallowRef<Row | null> = shallowRef(null)
  const form = reactive<RecordForm>({})
  const fields = ref<EditorFieldsHandle>()
  const title = computed(() => `${editing.value ? '编辑' : '新增'}${options.noun}`)
  const guard = useUnsavedForm(visible, () => form, saving)

  // 先填好再打开：未保存保护在打开的那一刻记录基线。
  function open(row: Row | null) {
    const values = (row ?? {}) as Record<string, unknown>
    for (const key of keys) form[key] = fieldText(values[key]) ?? options.defaults?.[key] ?? ''
    saveError.value = ''
    editing.value = row
    visible.value = true
  }

  /** 必填和跨字段规则都过了才返回 true；不过时提示已经落在对应字段上。 */
  async function validate(): Promise<boolean> {
    if (!await fields.value?.validate()) return false
    const problem = options.check?.(form)
    if (!problem) return true
    await fields.value?.setError(problem.key, problem.message)
    return false
  }

  async function save() {
    if (saving.value) return
    saveError.value = ''
    if (!await validate()) return
    saving.value = true
    try {
      const payload = { ...form }
      const row: Row | null = editing.value
      if (row) await options.update(row, payload)
      else await options.create(payload)
      ElMessage.success('已保存')
      visible.value = false
      await options.refresh()
    } catch (error) {
      if (isStaleConflict(error)) {
        saveError.value = CONFLICT_TEXT
        await options.refresh()
      } else {
        saveError.value = errorMessage(error, '保存失败，请检查后重试')
      }
    } finally {
      saving.value = false
    }
  }

  return {
    visible,
    saving,
    saveError,
    title,
    form,
    fields,
    guard,
    save,
    editing,
    openCreate: () => open(null),
    openEdit: (row: Row) => open(row),
  }
}
