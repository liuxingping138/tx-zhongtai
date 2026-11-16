<script setup lang="ts">
import { computed } from 'vue'

import { formatState, promptFields, refreshFormatBlock, splitFields } from '../shared/aiText'
import { missingFieldsWarning } from '../shared/outputFields'

/** 紧贴提示词编辑框底部的「输出字段」轨道：清晰区分左轨输入变量与输出字段，一键把 JSON 格式同步进提示词。 */
defineProps<{ canEdit: boolean }>()
const outputFields = defineModel<string>('outputFields', { required: true })
const content = defineModel<string>('content', { required: true })

const FIELD_DELIMITER = /[|｜,，、]/
const fields = computed({
  get: () => splitFields(outputFields.value),
  set: (value: string[] | undefined) => { outputFields.value = (value ?? []).join('|') },
})
const noFields = computed(() => missingFieldsWarning(content.value, fields.value))
const format = computed(() => formatState(content.value, fields.value))
const writtenFields = computed(() => promptFields(content.value)?.join('、') ?? '')

function writeFormat(): void {
  content.value = refreshFormatBlock(content.value, fields.value)
}
</script>

<template>
  <div
    class="out-dock"
    aria-label="输出字段设置"
  >
    <span class="out-dock__label">输出字段</span>
    <div class="out-dock__main">
      <el-input-tag
        v-model="fields"
        aria-label="输出字段"
        placeholder="输入期望 AI 返回的字段名回车（如：是否政策），留空则输出自由文本"
        size="small"
        :delimiter="FIELD_DELIMITER"
        :disabled="!canEdit"
        clearable
        draggable
      />
      <div class="out-dock__foot">
        <span
          v-if="noFields"
          class="is-warn"
          role="status"
        >{{ noFields }}</span>
        <span
          v-else-if="format === 'stale'"
          class="is-warn"
          role="status"
        >提示词里写的返回字段还是「{{ writtenFields }}」，和这里对不上，模型会按旧字段回</span>
        <span v-else>{{ fields.length ? `共 ${fields.length} 个字段，模型按 JSON 返回` : '未设固定字段，直接返回自由文本' }}{{ format === 'match' ? ' · 格式要求已对上' : '' }}</span>
        <el-button
          v-if="format !== 'match'"
          link
          size="small"
          :type="format === 'stale' ? 'warning' : 'primary'"
          :disabled="!canEdit || !fields.length"
          @click="writeFormat"
        >
          {{ format === 'stale' ? '更新提示词里的格式要求' : '把格式要求追加到提示词' }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.out-dock { display: grid; grid-template-columns: 56px minmax(0, 1fr); align-items: start; gap: 8px; padding: 8px 16px 9px; border-top: 1px solid var(--zt-divider); background: var(--zt-surface-subtle); }
.out-dock__label { color: var(--zt-ink-500); font-size: 12px; font-weight: 600; line-height: 26px; }
.out-dock__main { display: grid; gap: 4px; min-width: 0; }
.out-dock__foot { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 4px 12px; color: var(--zt-ink-500); font-size: 11.5px; }
.out-dock__foot .is-warn { color: var(--zt-warning-text); }
</style>
