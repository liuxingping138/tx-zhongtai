import { nextTick, reactive, watch, type Ref } from 'vue'
import type { FormInstance } from 'element-plus'
/** Shared text errors and first-error focus for Element Plus forms. */
export function useFieldValidation<T extends Record<string, string>>(values: T, form: Ref<FormInstance | undefined>) {
  const errors = reactive<Record<string, string>>({})
  watch(() => ({ ...values }), (value, previous) => {
    for (const key of Object.keys(errors)) if (value[key] !== previous[key]) delete errors[key]
  })
  async function validate(messages: Record<string, string>) {
    for (const key of Object.keys(errors)) delete errors[key]
    Object.assign(errors, Object.fromEntries(Object.entries(messages).filter(([, message]) => message)))
    if (!Object.keys(errors).length) return true
    await nextTick()
    const element = form.value?.$el.querySelector('[aria-invalid="true"]') as HTMLElement | undefined
    element?.focus()
    element?.scrollIntoView({ block: 'nearest' })
    return false
  }
  return { errors, validate }
}
