<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrowLeft,
  Check,
  CircleCheck,
  DocumentChecked,
  FullScreen,
  MoreFilled,
  Promotion,
  ScaleToOriginal,
} from '@element-plus/icons-vue'

import type { PromptTemplate } from '@/api/ai'
import { releaseEntry, releaseState } from './templateStatus'

/** 单行 52px Google 风格工作台命令栏：立体胶囊面包屑 + 可编辑标题 + 二元上线状态/版本微标 + 立体动作组。 */
const props = defineProps<{
  template: PromptTemplate | null
  dirty: boolean
  saving: boolean
  canEdit: boolean
  canRelease: boolean
  editorWide: boolean
  hideWideToggle: boolean
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
const rEntry = computed(() => releaseEntry(props.template, props.canRelease, 'header'))
const showMore = computed(() => Boolean(props.template && (props.canEdit || props.canRelease || props.template.release)))
const releaseHover = computed(() => {
  if (!rState.value) return ''
  if (rState.value.kind === 'offline') {
    return props.canRelease ? '当前尚未上线，点击右侧「发布上线」审核后生效' : '当前尚未上线，确认无误后请联系管理员上线'
  }
  return rState.value.detail ? `${rState.value.text}（线上：${rState.value.detail}）` : rState.value.text
})

const releaseBtnPrimary = computed(() =>
  Boolean(rEntry.value && (rEntry.value.emphasis === 'primary' || rEntry.value.emphasis === 'plain')))

function onMoreCommand(command: string): void {
  if (command === 'release') emit('open-release')
  else if (command === 'delete') emit('remove')
}

defineExpose({ focusTitle: () => titleInput.value?.focus() })
</script>

<template>
  <header class="ai-panel prompt-head">
    <nav
      class="prompt-head__crumb"
      aria-label="面包屑导航"
    >
      <router-link
        class="prompt-head__back"
        :to="{ name: 'ai-prompts' }"
      >
        <el-icon class="prompt-head__back-icon">
          <ArrowLeft />
        </el-icon>
        <span>提示词模板</span>
      </router-link>
      <span
        class="prompt-head__slash"
        aria-hidden="true"
      >/</span>
    </nav>

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
        v-else-if="!template"
        class="prompt-head__badge is-draft"
      >新草稿</span>
    </div>

    <div
      v-if="template && rState"
      class="prompt-head__lifecycle"
    >
      <div
        class="prompt-head__state-group"
        :title="releaseHover"
      >
        <template v-if="template.release">
          <span class="prompt-head__pill is-online"><i aria-hidden="true" />已上线</span>
          <span class="prompt-head__ver">v{{ template.release.release_no }}</span>
          <span
            v-if="template.release.unreleased_changes.length"
            class="prompt-head__diff"
          >有改动</span>
        </template>
        <span
          v-else
          class="prompt-head__pill is-offline"
        ><i aria-hidden="true" />未上线</span>
      </div>

      <el-button
        v-if="rEntry"
        class="prompt-head__btn"
        :type="releaseBtnPrimary ? 'primary' : undefined"
        :plain="releaseBtnPrimary && dirty"
        :icon="releaseBtnPrimary ? Promotion : DocumentChecked"
        @click="emit('open-release')"
      >
        {{ rEntry.label }}
      </el-button>
    </div>

    <div class="prompt-head__actions">
      <el-button
        v-if="!hideWideToggle"
        class="prompt-head__btn"
        :icon="editorWide ? ScaleToOriginal : FullScreen"
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
          class="prompt-head__btn prompt-head__more"
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
              {{ canRelease ? '上线审核与历史记录' : '查看线上版本与记录' }}
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

      <template v-if="canEdit">
        <el-button
          v-if="!template || dirty || saving"
          type="primary"
          class="prompt-head__btn"
          :loading="saving"
          :icon="Check"
          title="保存草稿（Ctrl/⌘ + S）"
          @click="emit('save')"
        >
          保存
        </el-button>
        <button
          v-else
          type="button"
          class="prompt-head__saved"
          disabled
          :title="`已保存 · ${template.updated_by_name} ${template.updated_at}（Ctrl/⌘ + S）`"
        >
          <el-icon><CircleCheck /></el-icon>
          <span>已保存</span>
        </button>
      </template>
    </div>
  </header>
</template>

<style scoped>
.prompt-head {
  display: flex; align-items: center; gap: 10px; min-height: 52px; padding: 8px 14px; flex: none;
  background: var(--zt-hero-gradient);
}
.prompt-head :deep(.el-button.prompt-head__btn) {
  min-height: 32px; height: 32px; margin: 0; padding: 0 12px; border-radius: 999px; font-size: 12.5px;
}
.prompt-head :deep(.el-button.prompt-head__more) { width: 32px; padding: 0; }

.prompt-head__crumb { display: inline-flex; align-items: center; gap: 8px; flex: none; }
.prompt-head__back {
  display: inline-flex; align-items: center; gap: 5px;
  height: 30px; padding: 0 11px; border: 1px solid var(--zt-border-strong); border-radius: 999px;
  background: var(--zt-btn-sec-bg); box-shadow: var(--zt-btn-sec-shadow);
  color: var(--zt-ink-900); font-size: 12.5px; font-weight: 550; text-decoration: none; white-space: nowrap;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease, transform 0.12s ease;
}
.prompt-head__back-icon { color: var(--zt-blue-600); font-size: 13px; }
.prompt-head__back:hover {
  border-color: var(--zt-blue-600); background: var(--zt-btn-sec-hover-bg);
  color: var(--zt-blue-600); box-shadow: var(--zt-btn-sec-hover-shadow); transform: translateY(-0.5px);
}
.prompt-head__slash { color: var(--zt-ink-400); font-size: 15px; font-weight: 400; user-select: none; }

.prompt-head__title-wrap {
  display: flex; align-items: center; gap: 8px; flex: 1; min-width: 140px;
}
.prompt-head__title {
  flex: 1; min-width: 110px; max-width: 460px; height: 32px; padding: 0 8px;
  border: 1px solid transparent; border-radius: 7px;
  background: transparent; color: var(--zt-ink-900);
  font: 650 15.5px/1.35 var(--zt-font); outline: none;
  transition: background-color 0.14s ease, border-color 0.14s ease, box-shadow 0.14s ease;
}
.prompt-head__title:hover:not([readonly]) { background: var(--zt-panel); border-color: var(--zt-border); }
.prompt-head__title:focus:not([readonly]) {
  border-color: var(--el-color-primary-light-5); background: var(--zt-panel);
  box-shadow: 0 0 0 2px var(--zt-focus-ring);
}
.prompt-head__title::placeholder { color: var(--zt-ink-400); font-weight: 500; }

.prompt-head__badge {
  flex: none; display: inline-flex; align-items: center; height: 22px; padding: 0 8px;
  border-radius: 999px; border: 1px solid var(--zt-border); background: var(--zt-surface-subtle);
  color: var(--zt-ink-500); font-size: 11.5px; font-weight: 600; white-space: nowrap;
}
.prompt-head__badge.is-dirty {
  border-color: var(--zt-warning-border); background: var(--zt-warning-soft); color: var(--zt-warning-text);
}
.prompt-head__badge.is-draft {
  border-color: var(--el-color-primary-light-7); background: var(--el-color-primary-light-9); color: var(--zt-blue-600);
}

.prompt-head__lifecycle {
  display: flex; align-items: center; gap: 8px; padding-left: 12px;
  border-left: 1px solid var(--zt-border); flex: none;
}
.prompt-head__state-group { display: inline-flex; align-items: center; gap: 5px; }
.prompt-head__pill {
  display: inline-flex; align-items: center; gap: 5px; height: 24px; padding: 0 9px;
  border-radius: 999px; font-size: 12px; font-weight: 600; white-space: nowrap;
}
.prompt-head__pill i { width: 6px; height: 6px; border-radius: 50%; flex: none; }
.prompt-head__pill.is-online {
  border: 1px solid var(--zt-success-border); background: var(--zt-success-soft); color: var(--zt-success-text);
}
.prompt-head__pill.is-online i { background: var(--zt-success); }
.prompt-head__pill.is-offline {
  border: 1px solid var(--zt-border); background: var(--zt-panel); color: var(--zt-ink-500); font-weight: 500;
}
.prompt-head__pill.is-offline i { background: var(--zt-muted-mark); }

.prompt-head__ver {
  display: inline-flex; align-items: center; height: 22px; padding: 0 6px;
  border: 1px solid var(--zt-border); border-radius: 5px; background: var(--zt-panel);
  color: var(--zt-ink-700); font-size: 11.5px; font-weight: 600; font-variant-numeric: tabular-nums;
}
.prompt-head__diff {
  display: inline-flex; align-items: center; height: 22px; padding: 0 7px;
  border: 1px solid var(--zt-warning-border); border-radius: 999px;
  background: var(--zt-warning-soft); color: var(--zt-warning-text);
  font-size: 11px; font-weight: 600; white-space: nowrap;
}

.prompt-head__actions { display: flex; align-items: center; gap: 6px; flex: none; }
.prompt-head__saved {
  display: inline-flex; align-items: center; gap: 4px; height: 32px; padding: 0 11px;
  border: 1px solid var(--zt-border); border-radius: 999px;
  background: var(--zt-panel); color: var(--zt-ink-500);
  font: 550 12px/1 var(--zt-font); white-space: nowrap; cursor: default;
}
.prompt-head__saved .el-icon { color: var(--zt-success); font-size: 14px; }
.prompt-head__danger-item { color: var(--zt-danger-text); font-weight: 500; }

@media (max-width: 960px) {
  .prompt-head { flex-wrap: wrap; }
  .prompt-head__lifecycle { border-left: 0; padding-left: 0; }
}
</style>
