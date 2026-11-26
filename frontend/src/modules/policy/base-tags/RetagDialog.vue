<script setup lang="ts">
import { computed } from 'vue'
import type { BaseTagItem } from '@/api/policy'
import BatchChoiceDialog, { type BatchChoice } from '@/components/BatchChoiceDialog.vue'
import { useAuthStore } from '@/stores/auth'
import { RETAG_CHOICES } from './fields'
import { submitRetag, type RetagSubmitOutcome } from './retag'

/** 重新打标的对话框：选放回哪个任务的待办、看清会发生什么。列表页和核对页共用；核对页传入当前行时按行状态置灰不可选的步骤。 */
const props = defineProps<{ ids: string[]; target?: string; row?: BaseTagItem | null; defaultStep?: string }>()
const emit = defineEmits<{ done: [result: RetagSubmitOutcome] }>()
const open = defineModel<boolean>({ required: true })

const auth = useAuthStore()
const canTrigger = computed(() => auth.canFull('system.scheduler') && auth.canFull('policy.ai_tagging'))
let lastOutcome: RetagSubmitOutcome = { queued: 0, triggered: false }

async function handleSubmit(step: string) {
  const outcome = await submitRetag(props.ids, step, canTrigger.value)
  lastOutcome = { queued: outcome.queued, triggered: outcome.triggered }
  return outcome
}

const choices = computed<BatchChoice[]>(() => {
  const row = props.row
  if (!row) return RETAG_CHOICES
  const canInterpret = row.need_interpret === '是'
  const hasInterpreted = canInterpret && row.ai_status !== '待解读' && row.ai_status !== '等待重新判断类型' && row.ai_status !== '类型判断失败'
  return RETAG_CHOICES.map((item) => {
    if (item.value === 'interpret' && !canInterpret) {
      return { ...item, disabled: true, disabledReason: '当前「是否解读」不是「是」，请先重新判断类型或将其改为「是」' }
    }
    if (item.value === 'opportunity' && !canInterpret) {
      return { ...item, disabled: true, disabledReason: '当前「是否解读」不是「是」，无法补市场机会' }
    }
    if (item.value === 'opportunity' && !hasInterpreted) {
      return { ...item, disabled: true, disabledReason: '当前尚未完成政策解读，请先执行「重新解读」' }
    }
    return item
  })
})
</script>

<template>
  <BatchChoiceDialog
    v-model="open"
    title="重新打标"
    :count="props.ids.length"
    :target="props.target"
    :default-value="props.defaultStep"
    prompt="重新打标的是："
    :choices="choices"
    :submit="handleSubmit"
    @done="emit('done', lastOutcome)"
  />
</template>
