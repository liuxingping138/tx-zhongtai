import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessageBox } from 'element-plus'

/** Keep a per-opening baseline so editing another row never inherits a stale dirty state. */
export function useUnsavedForm(visible: Ref<boolean>, value: () => unknown, saving: Ref<boolean>) {
  // 基线必须是响应式的：markSaved 后 dirty 要重新计算，否则保存成功后「未保存」提示还挂着。
  const baseline = ref('')
  let confirming: Promise<boolean> | undefined
  watch(visible, (open) => {
    if (open) baseline.value = JSON.stringify(value())
  }, { flush: 'sync' })
  const dirty = computed(() => visible.value && JSON.stringify(value()) !== baseline.value)

  /**
   * Call after an asynchronous form load or a successful save establishes a new clean value.
   * 传 snapshot 时以它为基线：保存请求在路上时又改了表单，基线是发出去的那份，表单仍算未保存。
   */
  function markSaved(snapshot?: unknown) {
    baseline.value = JSON.stringify(snapshot === undefined ? value() : snapshot)
  }

  async function canLeave(): Promise<boolean> {
    if (saving.value) return false
    if (!dirty.value) return true
    if (!confirming) {
      confirming = ElMessageBox.confirm('当前填写的内容尚未保存，离开后将丢失。', '放弃未保存的修改？', {
        type: 'warning',
        confirmButtonText: '放弃修改',
        cancelButtonText: '继续编辑',
        closeOnClickModal: false,
        distinguishCancelAndClose: true,
      }).then(() => true, () => false).finally(() => { confirming = undefined })
    }
    return confirming
  }

  async function close() {
    if (await canLeave()) visible.value = false
  }

  async function beforeClose(done: () => void) {
    if (await canLeave()) done()
  }

  function beforeUnload(event: BeforeUnloadEvent) {
    if (dirty.value || saving.value) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  onMounted(() => window.addEventListener('beforeunload', beforeUnload))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
  onBeforeRouteLeave(canLeave)
  return { dirty, markSaved, close, beforeClose, canLeave }
}
