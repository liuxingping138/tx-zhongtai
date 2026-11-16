<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { errorMessage } from '@/api/errors'

/** 勾选多条后的批量操作：选一个选项、看清会发生什么、确定。结果里有跳过的，逐条原因弹窗说明。 */
export interface BatchChoice {
  value: string
  label: string
  /** 选中后在下面说明这一项会做什么 */
  hint: string
  disabled?: boolean
  disabledReason?: string
}

export interface BatchResult {
  message: string
  skipped?: { reason: string; count: number }[]
}

const props = defineProps<{
  title: string
  count: number
  /** 「已勾选 N 条政策，」后面接的话，如「数据状态改为：」 */
  prompt: string
  /** 不是勾选来的（如核对页的当前这条）时开头写它，代替「已勾选 N 条」 */
  target?: string
  defaultValue?: string
  choices: BatchChoice[]
  submit: (value: string) => Promise<BatchResult>
}>()
const emit = defineEmits<{ done: [] }>()
const open = defineModel<boolean>({ required: true })
const value = ref('')
const saving = ref(false)
const hint = computed(() => {
  const found = props.choices.find(item => item.value === value.value)
  if (!found) return ''
  return found.disabledReason ? `${found.hint}（${found.disabledReason}）` : found.hint
})

watch(open, visible => {
  if (visible) {
    const preferred = props.defaultValue ? props.choices.find(item => item.value === props.defaultValue && !item.disabled) : undefined
    const firstEnabled = preferred ?? props.choices.find(item => !item.disabled) ?? props.choices[0]
    value.value = firstEnabled?.value ?? ''
  }
})

async function confirm(): Promise<void> {
  saving.value = true
  try {
    const result = await props.submit(value.value)
    open.value = false
    emit('done')
    if (result.skipped?.length) {
      const lines = result.skipped.map(item => `${item.count} 条：${item.reason}`).join('\n')
      await ElMessageBox.alert(`${result.message}\n\n跳过的：\n${lines}`, props.title, { confirmButtonText: '知道了', customClass: 'confirm-lines' }).catch(() => undefined)
    } else {
      ElMessage.success(result.message)
    }
  } catch (error) {
    ElMessage.error(errorMessage(error, '操作失败，请重试'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="open"
    :title="title"
    width="min(480px, calc(100vw - 32px))"
  >
    <p class="batch-choice__count">
      {{ target ?? `已勾选 ${count} 条` }}，{{ prompt }}
    </p>
    <el-radio-group
      v-model="value"
      class="batch-choice__options"
      :aria-label="title"
    >
      <el-radio
        v-for="item in choices"
        :key="item.value"
        :value="item.value"
        :disabled="item.disabled"
        :title="item.disabledReason"
      >
        {{ item.label }}<span
          v-if="item.disabledReason"
          class="batch-choice__disabled-note"
        >（{{ item.disabledReason }}）</span>
      </el-radio>
    </el-radio-group>
    <p class="batch-choice__hint">
      {{ hint }}
    </p>
    <template #footer>
      <el-button @click="open = false">
        取消
      </el-button>
      <el-button
        type="primary"
        :loading="saving"
        :disabled="!value"
        @click="confirm"
      >
        确定
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.batch-choice__count { margin: 0 0 12px; color: var(--zt-ink-900); }
.batch-choice__options { display: flex; flex-wrap: wrap; gap: 4px 0; }
.batch-choice__disabled-note { font-size: 12px; color: var(--zt-ink-500); }
.batch-choice__hint { min-height: 40px; margin: 12px 0 0; padding: 8px 12px; border-radius: 4px; background: var(--zt-soft); color: var(--zt-ink-700); font-size: 13px; line-height: 1.6; }
</style>
