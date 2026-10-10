/** 编辑表单的字段分组，GroupedFields 按它渲染，列表页的详情列也从它补齐。 */
export interface EditorField {
  key: string
  label: string
  maxLength?: number
  required?: boolean
  long?: boolean
  hint?: string
  placeholder?: string
  /** 取值固定的字段用下拉单选，不给自由输入。 */
  choices?: string[]
}

export interface EditorGroup {
  title: string
  hint: string
  fields: EditorField[]
}
