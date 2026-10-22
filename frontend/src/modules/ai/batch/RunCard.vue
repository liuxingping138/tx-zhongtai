<script setup lang="ts">
import type { AiModel, PromptTemplate } from '@/api/ai'
import ModelPicker from '../shared/ModelPicker.vue'

/** 批量提问上方的运行卡：选中模板的测试数据、码表、输出字段、模型一眼看全，提示词按需展开，确认后运行。 */
defineProps<{
  template: PromptTemplate | null
  models: AiModel[]
  runModel: AiModel | undefined
  blocker: string
  canRun: boolean
  starting: boolean
  testRows: number
}>()
const emit = defineEmits<{ start: [limit: number] }>()
const fallbackModel = defineModel<string>('fallbackModel', { required: true })
const thinking = defineModel<boolean>('thinking', { default: false })
</script>

<template>
  <section
    class="ai-panel run-card"
    aria-label="运行"
  >
    <p
      v-if="!template"
      class="run-card__empty"
    >
      从左边选一个模板。这里会列出它的测试数据、码表和输出字段，确认后再运行。
    </p>
    <template v-else>
      <header class="run-card__head">
        <h2>{{ template.title }}</h2>
        <span class="run-card__badge">{{ template.category_name }}类</span>
        <span
          v-if="template.release"
          class="run-card__badge run-card__badge--live"
        >第 {{ template.release.release_no }} 版已上线</span>
      </header>
      <dl class="run-card__facts">
        <div>
          <dt>测试数据</dt>
          <dd :title="template.excel_name">
            {{ template.excel_name ? `${template.excel_rows.toLocaleString()} 行` : '未上传 Excel' }}
          </dd>
        </div>
        <div>
          <dt>码表</dt>
          <dd>{{ template.code_table_name ? `系统${template.code_table_name}` : template.code_name || '不用码表' }}</dd>
        </div>
        <div class="run-card__fields">
          <dt>输出字段</dt>
          <dd>
            <span
              v-for="field in template.fields"
              :key="field"
              class="run-card__chip"
            >{{ field }}</span>
            <span v-if="!template.fields.length">未设置，结果里不会多出字段列</span>
          </dd>
        </div>
        <div>
          <dt>模型</dt>
          <dd v-if="template.model_id">
            {{ runModel?.name ?? template.model_id }}
          </dd>
          <dd v-else>
            <ModelPicker
              v-model="fallbackModel"
              :models="models"
              :show-thinking="false"
              size="small"
            />
          </dd>
        </div>
      </dl>
      <details class="run-card__prompt">
        <summary>查看提示词</summary>
        <pre>{{ template.content }}</pre>
      </details>
      <footer class="run-card__foot">
        <el-switch
          v-if="runModel?.supports_thinking"
          v-model="thinking"
          size="small"
          active-text="深度思考"
        />
        <span
          v-if="blocker"
          class="run-card__blocker"
          role="status"
        >{{ blocker }}</span>
        <span class="run-card__spacer" />
        <template v-if="canRun">
          <el-button
            :disabled="Boolean(blocker)"
            :loading="starting"
            @click="emit('start', testRows)"
          >
            先跑 {{ testRows }} 条看看
          </el-button>
          <el-button
            type="primary"
            :disabled="Boolean(blocker)"
            :loading="starting"
            @click="emit('start', 0)"
          >
            运行全部 {{ template.excel_rows ? `${template.excel_rows.toLocaleString()} 条` : '' }}
          </el-button>
        </template>
      </footer>
    </template>
  </section>
</template>

<style scoped>
.run-card { display: flex; flex-direction: column; }
.run-card__empty { margin: 0; padding: 28px 22px; color: var(--zt-ink-500); font-size: 13px; }
.run-card__head { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding: 16px 20px 0; }
.run-card__head h2 { margin: 0 4px 0 0; color: var(--zt-ink-900); font-size: 18px; font-weight: 600; }
.run-card__badge { padding: 1px 8px; border-radius: 4px; background: var(--zt-soft); color: var(--zt-ink-700); font-size: 12px; line-height: 20px; }
.run-card__badge--live { background: #e2f2eb; color: #2f7558; }
.run-card__facts { display: grid; grid-template-columns: repeat(4, minmax(0, auto)); justify-content: start; gap: 4px 36px; margin: 14px 0 0; padding: 0 20px; }
.run-card__facts div { min-width: 0; }
.run-card__facts dt { color: var(--zt-ink-500); font-size: 12px; }
.run-card__facts dd { margin: 4px 0 0; color: var(--zt-ink-900); font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-card__fields dd { display: flex; flex-wrap: wrap; gap: 4px; white-space: normal; }
.run-card__chip { padding: 0 8px; border-radius: 999px; background: #e3eefc; color: #2362c5; font-size: 12px; line-height: 22px; }
.run-card__prompt { margin: 14px 20px 0; }
.run-card__prompt summary { width: fit-content; color: var(--zt-blue-600); font-size: 13px; cursor: pointer; }
.run-card__prompt pre { max-height: 260px; margin: 8px 0 0; padding: 12px 14px; overflow: auto; border-radius: 6px; background: var(--zt-soft); color: var(--zt-ink-900); font: 13px/1.75 var(--zt-font); white-space: pre-wrap; }
.run-card__foot { display: flex; align-items: center; flex-wrap: wrap; gap: 10px 14px; margin-top: 16px; padding: 12px 20px; border-top: 1px solid var(--zt-border); background: #fafbfd; }
.run-card__foot .el-button { margin: 0; }
.run-card__blocker { color: var(--el-color-warning-dark-2); font-size: 13px; }
.run-card__spacer { flex: 1; }
@media (max-width: 1100px) {
  .run-card__facts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
