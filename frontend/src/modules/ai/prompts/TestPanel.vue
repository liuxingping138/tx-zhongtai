<script setup lang="ts">
import type { AiModel, BatchRun, PromptTemplate } from '@/api/ai'
import type { useAnswerStream } from '../shared/useAnswerStream'
import SampleRunPanel from './SampleRunPanel.vue'
import TrialPanel from './TrialPanel.vue'

/** 编辑页右栏：先「试发一条」边写边看，再「样本试跑」整批验一遍。两种都用左边的草稿。 */
defineProps<{
  answer: ReturnType<typeof useAnswerStream>
  template: PromptTemplate | null
  model: AiModel | undefined
  canRun: boolean
  dirty: boolean
}>()
const emit = defineEmits<{ run: []; 'sample-changed': [run: BatchRun] }>()
const tab = defineModel<'trial' | 'sample'>('tab', { required: true })
const thinking = defineModel<boolean>('thinking', { default: false })
const TABS = [{ key: 'trial', label: '试发一条' }, { key: 'sample', label: '样本试跑' }] as const
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
      <el-switch
        v-if="model?.supports_thinking"
        v-model="thinking"
        size="small"
        active-text="深度思考"
      />
    </div>
    <TrialPanel
      v-show="tab === 'trial'"
      id="test-pane-trial"
      role="tabpanel"
      aria-labelledby="test-tab-trial"
      :answer="answer"
      :model="model"
      :can-run="canRun"
      :has-excel="Boolean(template?.excel_name)"
      @run="emit('run')"
    />
    <SampleRunPanel
      v-show="tab === 'sample'"
      id="test-pane-sample"
      role="tabpanel"
      aria-labelledby="test-tab-sample"
      :template="template"
      :model="model"
      :thinking="thinking"
      :can-run="canRun"
      :dirty="dirty"
      @changed="run => emit('sample-changed', run)"
    />
  </aside>
</template>

<style scoped>
.test-panel { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.test-panel__head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 0 16px; border-bottom: 1px solid var(--zt-border); }
.test-panel__tabs { display: flex; gap: 20px; }
.test-panel__tabs button { position: relative; padding: 13px 0 11px; border: 0; background: none; color: var(--zt-ink-500); font: 600 14px/22px var(--zt-font); cursor: pointer; }
.test-panel__tabs button[aria-selected="true"] { color: var(--zt-ink-900); }
.test-panel__tabs button[aria-selected="true"]::after { content: ""; position: absolute; left: 0; right: 0; bottom: -1px; height: 2px; border-radius: 1px; background: var(--zt-blue-600); }
.test-panel__tabs button:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 2px; }
</style>
