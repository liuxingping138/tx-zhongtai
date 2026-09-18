import { computed, onBeforeUnmount, onMounted, watch, type Ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessageBox } from 'element-plus'

/** Keep a per-opening baseline so editing another row never inherits a stale dirty state. */
export function useUnsavedForm(visible: Ref<boolean>, value: () => unknown, saving: Ref<boolean>) {
  let baseline = ''
  let confirming: Promise<boolean> | undefined
  watch(visible, (open) => {
    if (open) baseline = JSON.stringify(value())
  }, { flush: 'sync' })
  const dirty = computed(() => visible.value && JSON.stringify(value()) !== baseline)

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
  return { dirty, close, beforeClose }
}
