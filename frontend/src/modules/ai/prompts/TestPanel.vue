<script setup lang="ts">
import { toRef } from 'vue'

import type { AiModel, BatchRun, PromptTemplate } from '@/api/ai'
import type { useAnswerStream } from '../shared/useAnswerStream'
import SampleRunPanel from './SampleRunPanel.vue'
import TrialPanel from './TrialPanel.vue'
import { useSampleRun } from './useSampleRun'

/**
 * 编辑页右栏：先「试发一条」边写边看，再「样本试跑」整批验一遍。两种都用左边的草稿。
 * 样本试跑里有问题的行能直接跳到试发、单独改到对；试发也拿这一行的试跑结果对照。
 */
const props = defineProps<{
  answer: ReturnType<typeof useAnswerStream>
  template: PromptTemplate | null
  model: AiModel | undefined
  content: string
  fields: string[]
  codeName: string
  canRun: boolean
  canExport: boolean
  dirty: boolean
}>()
const emit = defineEmits<{ run: []; upload: []; edit: []; 'sample-changed': [run: BatchRun] }>()
const tab = defineModel<'trial' | 'sample'>('tab', { required: true })
const wide = defineModel<boolean>('wide', { default: false })
const thinking = defineModel<boolean>('thinking', { default: false })
/** 试发测试样本的第几条，从 0 数 */
const row = defineModel<number>('row', { required: true })
const TABS = [{ key: 'trial', label: '试发一条' }, { key: 'sample', label: '样本试跑' }] as const
const sample = useSampleRun(toRef(props, 'template'), run => emit('sample-changed', run))

/** 样本试跑里点「试发这一行」：换到试发，选好那一行（试跑的行号从 1 数）。 */
function trialRow(number: number): void {
  row.value = number - 1
  wide.value = false
  tab.value = 'trial'
}
</script>

<template>
  <aside
    class="ai-panel test-panel"
    aria-label="测试"
  >
    <div class="test-panel__head">
      <div
        class="test-panel__tabs"
        role="tablist"
        aria-label="测试方式"
      >
        <button
          v-for="item in TABS"
          :id="`test-tab-${item.key}`"
          :key="item.key"
          type="button"
          role="tab"
          :aria-selected="tab === item.key"
          :aria-controls="`test-pane-${item.key}`"
          @click="tab = item.key"
        >
          {{ item.label }}
        </button>
      </div>
      <div class="test-panel__right">
        <el-switch
          v-if="model?.supports_thinking"
          v-model="thinking"
          size="small"
          active-text="深度思考"
        />
        <button
          v-if="tab === 'sample'"
          type="button"
          class="test-panel__wide"
          @click="wide = !wide"
        >
          {{ wide ? '恢复分栏' : '全屏看结果' }}
        </button>
      </div>
    </div>
    <TrialPanel
      v-show="tab === 'trial'"
      id="test-pane-trial"
      v-model:row="row"
      role="tabpanel"
      aria-labelledby="test-tab-trial"
      :answer="answer"
      :model="model"
      :can-run="canRun"
      :template="template"
      :content="content"
      :fields="fields"
      :code-name="codeName"
      :sample="sample"
      @run="emit('run')"
      @upload="emit('upload')"
      @sample="tab = 'sample'"
    />
    <SampleRunPanel
      v-show="tab === 'sample'"
      id="test-pane-sample"
      role="tabpanel"
      aria-labelledby="test-tab-sample"
      :sample="sample"
      :template="template"
      :model="model"
      :thinking="thinking"
      :can-run="canRun"
      :can-export="canExport"
      :dirty="dirty"
      @upload="emit('upload')"
      @trial="trialRow"
      @edit="emit('edit')"
    />
  </aside>
</template>

<style scoped>
.test-panel { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.test-panel__tabs { display: flex; gap: 4px; padding: 3px; border: 1px solid var(--zt-border); border-radius: 999px; background: var(--zt-soft); }
.test-panel__tabs button { position: relative; padding: 5px 14px; border: 0; border-radius: 999px; background: none; color: var(--zt-ink-500); font: 600 13px/18px var(--zt-font); cursor: pointer; transition: all .15s; }
.test-panel__tabs button[aria-selected="true"] { background: var(--zt-panel); color: var(--zt-blue-600); box-shadow: 0 1px 2px var(--zt-shadow-soft); }
.test-panel__tabs button:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 2px; }
.test-panel__head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 14px; border-bottom: 1px solid var(--zt-border); background: var(--zt-surface-subtle); }
.test-panel__right { display: flex; align-items: center; gap: 10px; }
.test-panel__wide { padding: 4px 10px; border: 1px solid var(--zt-border); border-radius: 999px; background: var(--zt-panel); color: var(--zt-ink-700); font: 500 12px/1.3 var(--zt-font); cursor: pointer; }
.test-panel__wide:hover { border-color: var(--zt-blue-600); color: var(--zt-blue-600); }
</style>
