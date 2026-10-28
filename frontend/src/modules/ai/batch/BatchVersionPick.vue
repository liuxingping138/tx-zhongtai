<script setup lang="ts">
import { computed } from 'vue'

import type { PromptTemplate, RunVersion } from '@/api/ai'
import { versionOptions, type RunSpec } from './batchVersion'

/** 新建批量任务的前两步：选模板、选跑哪一版（线上版本或当前草稿），并列出这一版要什么列、用什么模型。 */
const props = defineProps<{ templates: PromptTemplate[]; template: PromptTemplate | undefined; spec: RunSpec | null; disabled: boolean }>()
const templateId = defineModel<string>('templateId', { required: true })
const version = defineModel<RunVersion>('version', { required: true })

/** 能选的排前面；只能查看的也列出来，写清原因，免得找不到模板以为丢了。 */
const options = computed(() => props.templates
  .map(item => ({ item, reason: item.editable ? '' : '只能查看' }))
  .sort((a, b) => Number(Boolean(a.reason)) - Number(Boolean(b.reason))))
const versions = computed(() => (props.template ? versionOptions(props.template) : []))

function optionNote(item: PromptTemplate): string {
  if (!item.release) return `${item.category_name}，未上线，可跑草稿`
  return `${item.category_name}，第 ${item.release.release_no} 版在线${item.release.unreleased_changes.length ? '，草稿有改动' : ''}`
}
</script>

<template>
  <section class="new-task__step">
    <h3><span>1</span>选模板</h3>
    <el-select
      v-model="templateId"
      filterable
      placeholder="搜索模板名称"
      aria-label="任务模板"
      :disabled="disabled"
    >
      <el-option
        v-for="{ item, reason } in options"
        :key="item.id"
        :value="item.id"
        :label="item.title"
        :disabled="Boolean(reason)"
      >
        <span class="pick__option">
          <span>{{ item.title }}</span>
          <small>{{ reason || optionNote(item) }}</small>
        </span>
      </el-option>
    </el-select>
    <p class="new-task__hint">
      线上版本和当前草稿都能跑；草稿不用等管理员上线，调好模板就能拿这次的数据跑。
    </p>
  </section>
  <section
    v-if="template && spec"
    class="new-task__step"
  >
    <h3
      id="batch-version-title"
    >
      <span>2</span>跑哪一版
    </h3>
    <el-radio-group
      v-model="version"
      class="pick__versions"
      aria-labelledby="batch-version-title"
      :disabled="disabled"
    >
      <el-radio
        v-for="item in versions"
        :key="item.value"
        :value="item.value"
        :disabled="item.disabled"
        border
        class="pick__version"
      >
        <strong>{{ item.title }}</strong>
        <small>{{ item.detail }}</small>
        <small
          v-if="item.warning"
          class="pick__warning"
        >{{ item.warning }}</small>
      </el-radio>
    </el-radio-group>
    <div class="pick__spec">
      <dl>
        <dt>数据要有</dt>
        <dd class="pick__columns">
          <template v-if="spec.columns.length">
            <span
              v-for="column in spec.columns"
              :key="column"
            >{{ column }}</span>
          </template>
          <template v-else>
            不引用列，任意 .xlsx 都行
          </template>
        </dd>
        <dt>模型</dt><dd>{{ spec.modelName || '没选' }}</dd>
        <dt>输出字段</dt>
        <dd
          class="pick__fields"
          :title="spec.fields.join('、')"
        >
          {{ spec.fields.length ? `${spec.fields.length} 个：${spec.fields.join('、')}` : '未设置，保留模型原话' }}
        </dd>
        <dt>码表</dt><dd>{{ spec.code || '不用码表' }}{{ spec.code && version === 'draft' && template.code_table ? '（开始时取最新）' : '' }}</dd>
      </dl>
      <p class="pick__note">
        {{ version === 'draft'
          ? '开始时把这份草稿复制进任务，之后再改模板、上线新版本，都不影响这个任务。'
          : template.release?.unreleased_changes.length
            ? `模板草稿改了${template.release.unreleased_changes.join('、')}，还没上线；这次按${spec.label}跑。`
            : `这次按${spec.label}跑，和定时任务用的是同一版。` }}
      </p>
      <details>
        <summary>看{{ version === 'draft' ? '草稿' : spec.label }}的提示词</summary>
        <pre>{{ spec.content || '（空）' }}</pre>
      </details>
    </div>
    <p
      v-if="spec.problem"
      class="new-task__problem"
    >
      {{ spec.problem }}
    </p>
  </section>
</template>

<style scoped>
/* 和新建任务的其余步骤同一个样子（父组件的 scoped 样式进不到这里的多根节点）。 */
.new-task__step { padding: 4px 0 22px; margin-bottom: 20px; border-bottom: 1px solid var(--zt-border); }
.new-task__step h3 { display: flex; align-items: center; gap: 10px; margin: 0 0 12px; color: var(--zt-ink-900); font-size: 15px; font-weight: 650; }
.new-task__step h3 span { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: var(--zt-blue-600); color: var(--el-color-white); font-size: 12px; }
.new-task__step .el-select { width: 100%; }
.new-task__hint { margin: 8px 0 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.6; }
.new-task__problem { margin: 10px 0 0; color: var(--el-color-danger); font-size: 13px; }
.pick__option { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.pick__option small { color: var(--zt-ink-500); font-size: 12px; }
.pick__versions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; width: 100%; }
.pick__version.el-radio { align-items: flex-start; height: auto; margin: 0; padding: 12px 14px; white-space: normal; }
.pick__version :deep(.el-radio__input) { margin-top: 3px; }
.pick__version :deep(.el-radio__label) { display: flex; flex-direction: column; gap: 3px; min-width: 0; color: var(--zt-ink-500); font-size: 12px; font-weight: 400; line-height: 1.55; }
.pick__version strong { color: var(--zt-ink-900); font-size: 14px; }
.pick__version.is-checked { background: var(--el-color-primary-light-9); }
.pick__warning { color: var(--zt-warning-text); }
.pick__spec { margin-top: 12px; padding: 14px 16px; border-radius: 6px; background: var(--zt-soft); font-size: 13px; }
.pick__spec dl { display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 8px 12px; margin: 0; }
.pick__spec dt { color: var(--zt-ink-500); }
.pick__spec dd { margin: 0; overflow-wrap: anywhere; }
.pick__columns { display: flex; flex-wrap: wrap; gap: 6px; }
.pick__columns span { padding: 0 8px; border-radius: 4px; background: var(--el-color-primary-light-9); color: var(--zt-blue-700); line-height: 22px; }
.pick__fields { display: -webkit-box; overflow: hidden; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.pick__note { margin: 10px 0 0; color: var(--zt-ink-500); font-size: 12px; }
.pick__spec summary { margin-top: 10px; color: var(--zt-blue-600); cursor: pointer; }
.pick__spec pre { max-height: 260px; overflow: auto; margin: 8px 0 0; padding: 10px 12px; border-radius: 6px; background: var(--zt-panel); font: inherit; font-size: 13px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
