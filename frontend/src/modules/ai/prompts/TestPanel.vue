<script setup lang="ts">
import { computed, toRef } from 'vue'
import { FolderOpened, FullScreen, MagicStick, ScaleToOriginal, Upload } from '@element-plus/icons-vue'

import type { AiModel, BatchRun, PromptTemplate } from '@/api/ai'
import type { useAnswerStream } from '../shared/useAnswerStream'
import { starterPromptForCategory } from './promptStarter'
import SampleRunPanel from './SampleRunPanel.vue'
import TrialPanel from './TrialPanel.vue'
import { useSampleRun } from './useSampleRun'

/**
 * 编辑页右栏：先「试发一条」边写边看，再「样本试跑」整批验一遍。
 * 新建空白态展示 3 步快速冷启动引导卡（告别 75% 空黑框），支持直接取样本或填入分类标准骨架。
 */
const props = defineProps<{
  answer: ReturnType<typeof useAnswerStream>
  template: PromptTemplate | null
  category: string
  hasSampleTasks: boolean
  model: AiModel | undefined
  content: string
  fields: string[]
  codeName: string
  canRun: boolean
  canExport: boolean
  dirty: boolean
}>()
const emit = defineEmits<{
  run: []
  upload: []
  edit: []
  'open-sample-db': []
  'apply-starter': []
  'sample-changed': [run: BatchRun]
}>()

const tab = defineModel<'trial' | 'sample'>('tab', { required: true })
const wide = defineModel<boolean>('wide', { default: false })
const thinking = defineModel<boolean>('thinking', { default: false })
/** 试发测试样本的第几条，从 0 数 */
const row = defineModel<number>('row', { required: true })

const TABS = [{ key: 'trial', label: '试发一条' }, { key: 'sample', label: '样本试跑' }] as const
const sample = useSampleRun(toRef(props, 'template'), run => emit('sample-changed', run))

const starter = computed(() => starterPromptForCategory(props.category))
const showColdStart = computed(() =>
  !props.template
  && !props.content.trim()
  && !props.fields.length
  && !props.answer.messages.value.length
  && tab.value === 'trial')

function trialRow(number: number): void {
  row.value = number - 1
  wide.value = false
  tab.value = 'trial'
}
</script>

<template>
  <aside
    class="ai-panel test-panel"
    aria-label="测试与调试"
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
          class="row-action test-panel__wide"
          @click="wide = !wide"
        >
          <el-icon><ScaleToOriginal v-if="wide" /><FullScreen v-else /></el-icon>
          <span>{{ wide ? '恢复分栏' : '全屏看结果' }}</span>
        </button>
      </div>
    </div>

    <div
      v-if="showColdStart"
      class="new-guide"
      aria-label="新建模板快速起步引导"
    >
      <div class="new-guide__intro">
        <h3>三步完成新模板调试与上线</h3>
        <p>支持先导入样本对照表头写提示词，也可以一键填入行业标准骨架即刻试发。</p>
      </div>

      <ol class="new-guide__steps">
        <li class="new-guide__step">
          <div class="new-guide__step-head">
            <span class="new-guide__num">1</span>
            <span>绑定真实测试样本（可选）</span>
          </div>
          <p>给模板起好名字后导入样本，系统会自动保存草稿并提取表头列为 <code>@【变量】</code>。</p>
          <div
            v-if="canRun"
            class="new-guide__actions"
          >
            <el-button
              v-if="category === 'policy' && hasSampleTasks"
              size="small"
              type="primary"
              plain
              :icon="FolderOpened"
              @click="emit('open-sample-db')"
            >
              从政策库取数
            </el-button>
            <el-button
              size="small"
              :icon="Upload"
              @click="emit('upload')"
            >
              上传本地 Excel
            </el-button>
          </div>
        </li>

        <li class="new-guide__step">
          <div class="new-guide__step-head">
            <span class="new-guide__num">2</span>
            <span>编写提示词与输出 JSON 字段</span>
          </div>
          <p>在左栏输入 <code>@</code> 引用输入列或 <code>@【上传码表】</code>，在底部录入输出字段并同步 JSON 格式约束。</p>
          <div
            v-if="canRun"
            class="new-guide__actions"
          >
            <el-button
              size="small"
              type="primary"
              :icon="MagicStick"
              @click="emit('apply-starter')"
            >
              {{ starter.buttonLabel }}
            </el-button>
          </div>
        </li>

        <li class="new-guide__step">
          <div class="new-guide__step-head">
            <span class="new-guide__num">3</span>
            <span>单条试发 → 样本试跑 → 审核上线</span>
          </div>
          <p>按 <code>Ctrl/⌘ + Enter</code> 验证单条流式解析，再切换到「样本试跑」批量回归对比后提交上线。</p>
        </li>
      </ol>
    </div>

    <TrialPanel
      v-show="tab === 'trial' && !showColdStart"
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
      :wide="wide"
      :can-run="canRun"
      :can-export="canExport"
      :dirty="dirty"
      :active-row="row + 1"
      @upload="emit('upload')"
      @trial="trialRow"
      @edit="emit('edit')"
    />
  </aside>
</template>

<style scoped>
.test-panel { display: flex; flex-direction: column; min-height: 0; min-width: 0; overflow: hidden; }
.test-panel__head {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  min-height: 44px; padding: 7px 12px; flex: none;
  border-bottom: 1px solid var(--zt-border); background: var(--zt-hero-gradient);
}
.test-panel__tabs {
  display: inline-flex; gap: 3px; padding: 3px;
  border: 1px solid var(--zt-border); border-radius: 999px; background: var(--zt-soft);
}
.test-panel__tabs button {
  padding: 4px 13px; border: 0; border-radius: 999px; background: none;
  color: var(--zt-ink-500); font: 600 12.5px/18px var(--zt-font); cursor: pointer; transition: all 0.15s;
}
.test-panel__tabs button[aria-selected="true"] {
  background: var(--zt-panel); color: var(--zt-blue-600); box-shadow: 0 1px 2px var(--zt-shadow-soft);
}
.test-panel__tabs button:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 2px; }
.test-panel__right { display: flex; align-items: center; gap: 8px; }
.test-panel__wide .el-icon { color: var(--zt-blue-600); font-size: 13px; }

/* 新建模板 3 步冷启动引导卡 */
.new-guide {
  display: flex; flex-direction: column; gap: 12px; flex: 1; min-height: 0; overflow-y: auto;
  padding: 16px; background: var(--zt-hero-gradient);
}
.new-guide__intro h3 { margin: 0 0 4px; color: var(--zt-ink-900); font-size: 14.5px; font-weight: 650; }
.new-guide__intro p { margin: 0; color: var(--zt-ink-500); font-size: 12.5px; line-height: 1.55; }
.new-guide__steps { display: flex; flex-direction: column; gap: 10px; margin: 0; padding: 0; list-style: none; }
.new-guide__step {
  display: flex; flex-direction: column; gap: 6px; padding: 12px 14px;
  border: 1px solid var(--zt-border); border-radius: 10px; background: var(--zt-panel); box-shadow: var(--zt-shadow);
}
.new-guide__step-head { display: flex; align-items: center; gap: 8px; color: var(--zt-ink-900); font-size: 13px; font-weight: 600; }
.new-guide__num {
  display: inline-grid; place-items: center; width: 20px; height: 20px; border-radius: 5px;
  background: var(--el-color-primary-light-9); color: var(--zt-blue-600);
  font-size: 11.5px; font-weight: 700; font-variant-numeric: tabular-nums; flex: none;
}
.new-guide__step p { margin: 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.55; }
.new-guide__step code {
  padding: 1px 4px; border-radius: 4px; background: var(--zt-surface-subtle);
  color: var(--zt-ink-700); font-size: 11.5px;
}
.new-guide__actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 2px; }
.new-guide__actions .el-button { margin: 0; }
</style>
