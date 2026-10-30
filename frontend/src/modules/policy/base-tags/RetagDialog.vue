<script setup lang="ts">
import BatchChoiceDialog from '@/components/BatchChoiceDialog.vue'
import { RETAG_CHOICES } from './fields'
import { submitRetag } from './retag'

/** 重新打标的对话框：选放回哪个任务的待办、看清会发生什么。列表页和核对页共用。 */
const props = defineProps<{ ids: string[]; target?: string }>()
const emit = defineEmits<{ done: [] }>()
const open = defineModel<boolean>({ required: true })
</script>

<template>
  <BatchChoiceDialog
    v-model="open"
    title="重新打标"
    :count="props.ids.length"
    :target="props.target"
    prompt="重新打标的是："
    :choices="RETAG_CHOICES"
    :submit="(step) => submitRetag(props.ids, step)"
    @done="emit('done')"
  />
</template>
