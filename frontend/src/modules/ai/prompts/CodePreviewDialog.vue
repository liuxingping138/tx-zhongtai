<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { previewSystemCode, previewUploadedCode, type CodePreview } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { CODE_TABLE_FIELD } from '../shared/aiText'

/**
 * 看一眼码表：系统码表按键实时取（不用先保存模板），上传的按模板读。
 * 写清整份多大：每次提问都把整份放进 @【上传码表】，码表越大每条越贵。
 */
const props = defineProps<{ systemKey: string; promptId: string }>()
const open = defineModel<boolean>({ required: true })
const preview = ref<CodePreview | null>(null)
const loading = ref(false)
const failure = ref('')

const shown = computed(() => (preview.value ? preview.value.head.split('\n').length : 0))
const size = computed(() => {
  const chars = preview.value?.chars ?? 0
  return chars >= 10000 ? `约 ${(chars / 10000).toFixed(1)} 万字` : `${chars} 字`
})

watch(open, async visible => {
  if (!visible) return
  preview.value = null
  failure.value = ''
  loading.value = true
  try {
    preview.value = await (props.systemKey ? previewSystemCode(props.systemKey) : previewUploadedCode(props.promptId))
  } catch (error) {
    failure.value = errorMessage(error, '码表暂时取不到，请稍后再试')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <el-dialog
    v-model="open"
    :title="preview ? `码表预览：${preview.name}` : '码表预览'"
    width="min(760px, 92vw)"
  >
    <div
      v-loading="loading"
      class="code-preview"
    >
      <el-alert
        v-if="failure"
        :title="failure"
        type="error"
        :closable="false"
        show-icon
      />
      <template v-else-if="preview">
        <p class="code-preview__meta">
          共 {{ preview.lines }} 行、{{ size }}。每次提问都会把整份放进 @【{{ CODE_TABLE_FIELD }}】的位置，码表越大，每条花的钱越多。
        </p>
        <pre
          class="code-preview__text"
          aria-label="码表内容"
        >{{ preview.head }}</pre>
        <p
          v-if="preview.truncated"
          class="code-preview__meta"
        >
          只列出前 {{ shown }} 行，其余 {{ preview.lines - shown }} 行没显示。
        </p>
      </template>
    </div>
  </el-dialog>
</template>

<style scoped>
.code-preview { display: grid; gap: 10px; min-height: 120px; }
.code-preview__meta { margin: 0; color: var(--zt-ink-500); font-size: 13px; line-height: 1.7; }
.code-preview__text { max-height: 420px; overflow: auto; margin: 0; padding: 12px 14px; border-radius: 6px; background: var(--zt-soft); color: var(--zt-ink-900); font: 13px/1.7 ui-monospace, Menlo, Consolas, monospace; white-space: pre; tab-size: 16; }
</style>
