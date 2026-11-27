export interface SharedMetaFieldSpec {
  key: string
  label: string
  required?: boolean
  span?: boolean
  kind: 'input' | 'textarea' | 'select' | 'multi' | 'date'
  options?: readonly string[]
  clearable?: boolean
  allowCreate?: boolean
  maxlength?: number
  placeholder?: string
  rows?: number
}

export interface SummaryFact {
  label: string
  value: string
}

export interface ExtraStatusTag {
  label: string
  type: '' | 'primary' | 'success' | 'warning' | 'danger' | 'info'
}
