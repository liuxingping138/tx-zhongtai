<script setup lang="ts">
import type { RunRow } from '@/api/ai'
import { answerLines, isProblem } from './sampleView'

/** 逐行表格里展开的一行：这一行的输入、这次的回答、上次的回答并排对照。 */
defineProps<{ row: RunRow; columns: string[]; fields: string[]; runNo: number; compareNo: number; canRun: boolean }>()
const emit = defineEmits<{ trial: [] }>()
</script>

<template>
  <div class="detail-wrap">
    <div class="detail">
      <section>
        <h4>这一行的输入</h4>
        <dl>
          <template
            v-for="column in columns"
            :key="column"
          >
            <dt>{{ column }}</dt><dd>{{ row.inputs[column] || '—' }}</dd>
          </template>
        </dl>
      </section>
      <section :class="{ 'is-problem': isProblem(row) }">
        <h4>这次的回答（第 {{ runNo }} 次）</h4>
        <pre>{{ answerLines(row, fields) }}</pre>
      </section>
      <section v-if="row.previous">
        <h4>上次的回答（第 {{ compareNo }} 次）</h4>
        <pre>{{ answerLines(row.previous, fields) }}</pre>
      </section>
    </div>
    <el-button
      v-if="canRun"
      size="small"
      class="detail__trial"
      @click.stop="emit('trial')"
    >
      试发这一行
    </el-button>
  </div>
</template>

<style scoped>
/* 输出字段多时表格远宽于抽屉，展开行锁在抽屉可视宽度内，三栏对照不会被撑到屏幕右侧外。 */
.detail-wrap { position: sticky; left: 52px; width: min(1040px, calc(92vw - 80px)); max-width: calc(100vw - 80px); }
.detail { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
.detail section { min-width: 0; padding: 12px 14px; border: 1px solid var(--zt-border); border-radius: 6px; background: var(--zt-panel); }
.detail section.is-problem { border-color: var(--zt-warning-border); }
.detail h4 { margin: 0 0 8px; color: var(--zt-ink-500); font-size: 12px; font-weight: 600; }
.detail section.is-problem h4 { color: var(--zt-warning-text); }
.detail dl { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 4px 10px; margin: 0; font-size: 13px; }
.detail dt { color: var(--zt-ink-500); }
.detail dd { margin: 0; color: var(--zt-ink-900); word-break: break-all; }
.detail pre { margin: 0; color: var(--zt-ink-900); font: 13px/1.7 var(--zt-font); white-space: pre-wrap; word-break: break-all; }
.detail__trial { margin-top: 10px; }
</style>
