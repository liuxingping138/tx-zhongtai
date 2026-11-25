<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowLeft, MoreFilled } from '@element-plus/icons-vue'

import type { PromptTemplate } from '@/api/ai'
import { releaseState } from './templateStatus'

/** 单行 48px 工作台顶栏：整合返回、标题、保存状态、内联上线生命周期、专注编辑与低频更多菜单。 */
const props = defineProps<{
  template: PromptTemplate | null
  dirty: boolean
  saving: boolean
  canEdit: boolean
  canRelease: boolean
  editorWide: boolean
  hideWideToggle: boolean
  releaseActionLabel: string
}>()

const emit = defineEmits<{
  save: []
  remove: []
  'open-release': []
  'toggle-wide': []
}>()

const title = defineModel<string>('title', { required: true })
const titleInput = ref<HTMLInputElement | null>(null)

const rState = computed(() => (props.template ? releaseState(props.template) : null))
const showMore = computed(() => Boolean(props.template && (props.canEdit || props.canRelease || props.template.release)))
const releaseHover = computed(() => {
  if (!rState.value) return ''
  return rState.value.detail ? `${rState.value.text}（线上：${rState.value.detail}）` : rState.value.text
})

function onMoreCommand(command: string): void {
  if (command === 'release') emit('open-release')
  else if (command === 'delete') emit('remove')
}

defineExpose({ focusTitle: () => titleInput.value?.focus() })
</script>

<template>
  <header class="ai-panel prompt-head">
    <router-link
      class="prompt-head__back"
      aria-label="返回模板列表"
      :to="{ name: 'ai-prompts' }"
    >
      <el-icon><ArrowLeft /></el-icon>列表
    </router-link>

    <div class="prompt-head__title-wrap">
      <input
        ref="titleInput"
        v-model="title"
        class="prompt-head__title"
        maxlength="255"
        aria-label="模板名称"
        :placeholder="template ? '输入模板名称…' : '给新模板起个名字（如：政策奖补条款提取）'"
        :readonly="!canEdit"
      >
      <span
        v-if="!canEdit"
        class="prompt-head__badge"
      >只读</span>
      <span
        v-else-if="dirty"
        class="prompt-head__badge is-dirty"
      >未保存</span>
      <span
        v-else-if="template"
        class="prompt-head__meta"
        :title="`${template.updated_by_name} · ${template.updated_at}`"
      >已保存</span>
      <span
        v-else
        class="prompt-head__meta"
      >新草稿</span>
    </div>

    <div
      v-if="template && rState"
      class="prompt-head__lifecycle"
    >
      <span
        class="prompt-head__release"
        :class="`is-${rState.kind}`"
        :title="releaseHover"
      >{{ rState.compact }}</span>
      <el-button
        v-if="releaseActionLabel"
        size="small"
        :type="rState.kind === 'changed' && canRelease ? 'primary' : undefined"
        :plain="rState.kind === 'changed' && canRelease"
        @click="emit('open-release')"
      >
        {{ releaseActionLabel }}
      </el-button>
    </div>

    <div class="prompt-head__actions">
      <el-button
        v-if="!hideWideToggle"
        size="small"
        @click="emit('toggle-wide')"
      >
        {{ editorWide ? '恢复分栏' : '专注编辑' }}
      </el-button>

      <el-dropdown
        v-if="showMore"
        trigger="click"
        @command="onMoreCommand"
      >
        <el-button
          size="small"
          :icon="MoreFilled"
          aria-label="更多模板操作"
          title="更多操作"
        />
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-if="canRelease || template?.release"
              command="release"
            >
              查看上线版本与记录
            </el-dropdown-item>
            <el-dropdown-item
              v-if="canEdit"
              command="delete"
              :disabled="Boolean(template?.release)"
              :divided="Boolean(canRelease || template?.release)"
            >
              <span :class="{ 'prompt-head__danger-item': !template?.release }">
                {{ template?.release ? '删除模板（已上线需先下线）' : '删除此模板…' }}
              </span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <el-button
        v-if="canEdit"
        type="primary"
        size="small"
        :loading="saving"
        :disabled="Boolean(template) && !dirty"
        title="Ctrl/⌘ + S"
        @click="emit('save')"
      >
        保存
      </el-button>
    </div>
  </header>
</template>

<style scoped>
.prompt-head {
  display: flex; align-items: center; gap: 10px; min-height: 48px; padding: 6px 14px; flex: none;
}
.prompt-head :deep(.el-button) { margin: 0; border-radius: 8px; }

.prompt-head__back {
  display: inline-flex; flex: none; align-items: center; gap: 4px;
  height: 28px; padding: 0 10px; border: 1px solid var(--zt-border); border-radius: 8px;
  background: var(--zt-surface-subtle); color: var(--zt-ink-700);
  font-size: 12.5px; font-weight: 500; text-decoration: none; white-space: nowrap;
  transition: border-color 0.14s ease, color 0.14s ease;
}
.prompt-head__back:hover { border-color: var(--zt-border-strong); color: var(--zt-blue-600); }

.prompt-head__title-wrap {
  display: flex; align-items: center; gap: 8px; flex: 1; min-width: 140px;
}
.prompt-head__title {
  flex: 1; min-width: 110px; max-width: 460px; height: 32px; padding: 0 8px;
  border: 1px solid transparent; border-radius: 7px;
  background: transparent; color: var(--zt-ink-900);
  font: 600 16px/1.35 var(--zt-font); outline: none;
  transition: background-color 0.14s ease, border-color 0.14s ease;
}
.prompt-head__title:hover:not([readonly]) { background: var(--zt-surface-subtle); }
.prompt-head__title:focus:not([readonly]) {
  border-color: var(--el-color-primary-light-5); background: var(--zt-panel);
  box-shadow: 0 0 0 2px var(--zt-focus-ring);
}
.prompt-head__title::placeholder { color: var(--zt-ink-400); font-weight: 500; }

.prompt-head__meta { flex: none; color: var(--zt-ink-400); font-size: 12px; white-space: nowrap; }
.prompt-head__badge {
  flex: none; display: inline-flex; align-items: center; height: 21px; padding: 0 7px;
  border-radius: 5px; background: var(--zt-surface-subtle); color: var(--zt-ink-500);
  font-size: 11.5px; font-weight: 600; white-space: nowrap;
}
.prompt-head__badge.is-dirty {
  border: 1px solid var(--zt-warning-border); background: var(--zt-warning-soft); color: var(--zt-warning-text);
}

.prompt-head__lifecycle {
  display: flex; align-items: center; gap: 8px; padding-left: 12px;
  border-left: 1px solid var(--zt-divider); flex: none;
}
.prompt-head__release {
  display: inline-flex; align-items: center; gap: 5px;
  color: var(--zt-ink-500); font-size: 12.5px; white-space: nowrap;
}
.prompt-head__release::before {
  content: ""; width: 6.5px; height: 6.5px; border-radius: 50%; background: var(--zt-muted-mark);
}
.prompt-head__release.is-online { color: var(--zt-success-text); font-weight: 500; }
.prompt-head__release.is-online::before { background: var(--zt-success); }
.prompt-head__release.is-changed { color: var(--zt-warning-text); font-weight: 500; }
.prompt-head__release.is-changed::before { background: var(--zt-warning); }

.prompt-head__actions { display: flex; align-items: center; gap: 6px; flex: none; }
.prompt-head__danger-item { color: var(--zt-danger-text); font-weight: 500; }

@media (max-width: 900px) {
  .prompt-head { flex-wrap: wrap; }
  .prompt-head__lifecycle { border-left: 0; padding-left: 0; }
}
</style>
