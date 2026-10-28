<script setup lang="ts">
import { computed, h, nextTick, ref, type FunctionalComponent } from 'vue'

import { CODE_TABLE_FIELD, insertMention, mentionAt, mentionOptions } from '../shared/aiText'
import { promptSegments, unusedColumns, usedVariables, type PromptSegment, type VariableState } from './promptVariables'

/**
 * 写提示词的编辑器：@【列名】在文字底下直接画成标记——能替换的蓝色、码表青色、Excel 里找不到的琥珀色，
 * 还没传测试样本时列名标灰（没法核对，不算错）。写错列名不用等试发就能看出来。
 * 输入 @ 在光标处弹出列名；还没传样本时弹框和变量栏里直接给上传入口。Ctrl/⌘ + Enter 试发，Ctrl/⌘ + S 保存。
 *
 * 做法是常见的「背景层 + 透明 textarea」：背景层和 textarea 同字体、同内边距、同换行规则，
 * 文字透明只画标记底色，textarea 在上面负责输入和光标，滚动时同步背景层。
 */
// 背景层逐段输出文字和标记。用渲染函数而不是模板：模板里标签之间的换行会被压成空格，背景层就和输入框错位了。
// 渲染函数生成的 mark 不带本组件的作用域标识，样式里要用 :deep(mark)。
const MirrorText: FunctionalComponent<{ parts: PromptSegment[] }> = ({ parts }) =>
  parts.map(part => (part.state ? h('mark', { class: `is-${part.state}` }, part.text) : part.text))
MirrorText.props = ['parts']

/** codeName：模板现在用的码表（系统码表名或上传的文件名），空表示没选码表 */
const props = withDefaults(defineProps<{ headers: string[]; codeName: string; disabled?: boolean }>(), { disabled: false })
const emit = defineEmits<{ run: []; save: []; upload: [] }>()
const text = defineModel<string>({ required: true })

const area = ref<HTMLTextAreaElement | null>(null)
const backdrop = ref<HTMLElement | null>(null)
const caretMark = ref<HTMLElement | null>(null)
const trigger = ref<{ at: number; keyword: string; caret: number } | null>(null)
const active = ref(0)
const popup = ref({ top: 0, left: 0 })

const hasCode = computed(() => Boolean(props.codeName))
const options = computed(() => (trigger.value ? mentionOptions(props.headers, hasCode.value, trigger.value.keyword) : []))
const before = computed(() => promptSegments(trigger.value ? text.value.slice(0, trigger.value.caret) : text.value, props.headers, hasCode.value))
const after = computed(() => (trigger.value ? promptSegments(text.value.slice(trigger.value.caret), props.headers, hasCode.value) : []))
const used = computed(() => usedVariables(text.value, props.headers, hasCode.value))
const candidates = computed(() => unusedColumns(text.value, props.headers))
const missing = computed(() => used.value.filter(item => item.state === 'missing').length)
const noCode = computed(() => used.value.some(item => item.state === 'nocode'))
const titles = computed<Record<VariableState, string>>(() => ({
  column: 'Excel 列，逐行换成该行的值',
  code: `码表全文：${props.codeName}`,
  pending: '还没传测试样本，传了才能核对这一列',
  missing: 'Excel 里没有这一列，提问时会原样留在提示词里',
  nocode: '还没选码表：在下面「码表」里选系统码表或上传文件',
}))
const BADGES: Partial<Record<VariableState, string>> = { missing: '找不到', nocode: '没选码表' }
/** 弹框最宽多少（和样式里的 max-width 一致）：靠右输入 @ 时往左挪，不伸出编辑区 */
const MENU_WIDTH = 380

function syncScroll(): void {
  if (backdrop.value && area.value) backdrop.value.scrollTop = area.value.scrollTop
}

async function detect(): Promise<void> {
  const element = area.value
  if (!element || props.disabled) return
  const found = mentionAt(element.value, element.selectionStart)
  trigger.value = found ? { ...found, caret: element.selectionStart } : null
  active.value = 0
  if (!found) return
  await nextTick()
  // 背景层在光标处放了一个空标记，取它的位置就是光标位置。
  const mark = caretMark.value
  if (mark) popup.value = { top: mark.offsetTop - element.scrollTop + 24, left: Math.max(0, Math.min(mark.offsetLeft, element.clientWidth - MENU_WIDTH)) }
}

async function place(next: { text: string; caret: number }): Promise<void> {
  text.value = next.text
  trigger.value = null
  await nextTick()
  area.value?.focus()
  area.value?.setSelectionRange(next.caret, next.caret)
}

async function choose(field: string): Promise<void> {
  const element = area.value
  if (!element || !trigger.value || !field) return
  await place(insertMention(element.value, trigger.value.at, element.selectionStart, field))
}

/** 点变量栏里的列名：插在光标处（没聚焦过就插到末尾）。 */
async function insertAtCursor(field: string): Promise<void> {
  const element = area.value
  const caret = element && document.activeElement === element ? element.selectionStart : text.value.length
  await place(insertMention(text.value, caret, caret, field))
}

function move(step: number): void {
  const count = options.value.length
  active.value = (active.value + step + count) % count
}

/** Ctrl/⌘ + Enter 试发、Ctrl/⌘ + S 保存。处理了返回 true。 */
function shortcut(event: KeyboardEvent): boolean {
  if (!(event.metaKey || event.ctrlKey)) return false
  if (event.key === 'Enter') emit('run')
  else if (event.key.toLowerCase() === 's') emit('save')
  else return false
  event.preventDefault()
  return true
}

const MENU_KEYS: Record<string, () => void> = {
  ArrowDown: () => move(1),
  ArrowUp: () => move(-1),
  Enter: () => void choose(options.value[active.value] ?? ''),
  Tab: () => void choose(options.value[active.value] ?? ''),
}

function onKeydown(event: KeyboardEvent): void {
  if (event.isComposing || shortcut(event) || !trigger.value) return
  if (event.key === 'Escape') {
    trigger.value = null
    event.preventDefault()
    return
  }
  const action = MENU_KEYS[event.key]
  if (action && options.value.length) {
    action()
    event.preventDefault()
  }
}

/** 样本试跑抽屉里点「回去改提示词」：光标放回编辑框。 */
defineExpose({ focus: () => area.value?.focus() })
</script>

<template>
  <div class="prompt-editor">
    <div class="prompt-editor__surface">
      <div
        ref="backdrop"
        class="prompt-editor__backdrop"
        aria-hidden="true"
      >
        <div class="prompt-editor__mirror">
          <MirrorText :parts="before" />
          <span
            v-if="trigger"
            ref="caretMark"
          />
          <MirrorText :parts="after" />
        </div>
      </div>
      <textarea
        ref="area"
        v-model="text"
        class="prompt-editor__input"
        aria-label="提示词内容"
        placeholder="写下要让模型做的事。输入 @ 插入测试样本 Excel 的列名，跑的时候逐行换成该行的值；@【上传码表】插入码表全文，系统码表和上传的码表都用它。"
        spellcheck="false"
        :readonly="disabled"
        @input="detect"
        @click="detect"
        @keydown="onKeydown"
        @scroll="syncScroll"
        @blur="trigger = null"
      />
      <ul
        v-if="trigger"
        class="prompt-editor__menu"
        role="listbox"
        aria-label="可插入的变量"
        :style="{ top: `${popup.top}px`, left: `${popup.left}px` }"
      >
        <li
          v-if="!options.length && headers.length"
          class="prompt-editor__menu-hint"
        >
          没有匹配的列名
        </li>
        <li
          v-for="(option, index) in options"
          :key="option"
          role="option"
          :aria-selected="index === active"
          :class="{ 'is-active': index === active }"
          @mousedown.prevent="choose(option)"
        >
          <span class="prompt-editor__menu-token">@【{{ option }}】</span><small v-if="option === CODE_TABLE_FIELD">码表全文 · {{ codeName }}</small>
        </li>
        <li
          v-if="!headers.length"
          class="prompt-editor__menu-action"
          role="option"
          aria-selected="false"
          @mousedown.prevent="emit('upload')"
        >
          上传测试样本 Excel，列名就能插
        </li>
      </ul>
    </div>
    <div
      class="prompt-editor__vars"
      aria-label="提示词里的变量"
    >
      <span class="prompt-editor__vars-label">变量</span>
      <span
        v-for="item in used"
        :key="item.name"
        class="prompt-editor__var"
        :class="`is-${item.state}`"
        :title="titles[item.state]"
      >{{ item.name }}<small>{{ BADGES[item.state] ?? (item.count > 1 ? `×${item.count}` : '') }}</small></span>
      <button
        v-for="column in candidates"
        :key="column"
        type="button"
        class="prompt-editor__add"
        :disabled="disabled"
        :title="`插入 @【${column}】`"
        @click="insertAtCursor(column)"
      >
        + {{ column }}
      </button>
      <template v-if="!headers.length">
        <el-button
          v-if="!disabled"
          link
          type="primary"
          size="small"
          @click="emit('upload')"
        >
          上传测试样本 Excel
        </el-button>
        <span class="prompt-editor__vars-hint">{{ disabled ? '还没有测试样本' : '列名会出现在这里，点一下就插进提示词' }}</span>
      </template>
      <span
        v-if="missing || noCode"
        class="prompt-editor__warn"
        role="status"
      >{{ [noCode ? '用了码表变量，但还没选码表' : '', missing ? `${missing} 个变量在 Excel 里找不到` : ''].filter(Boolean).join('；') }}</span>
    </div>
  </div>
</template>

<style scoped>
.prompt-editor { display: flex; flex-direction: column; }
/* 输入框跟着内容长高、自己不滚动：高度由底下同字体的高亮层撑开，整个左栏只有一条滚动条。 */
.prompt-editor__surface { position: relative; flex: 1 0 auto; min-height: 260px; }
.prompt-editor__backdrop, .prompt-editor__input {
  margin: 0; padding: 18px 22px; border: 0;
  font: 14px/1.85 var(--zt-font); letter-spacing: 0.01em; white-space: pre-wrap; overflow-wrap: anywhere; word-break: normal;
}
.prompt-editor__backdrop { position: relative; pointer-events: none; color: transparent; }
.prompt-editor__mirror { min-height: 100%; padding-bottom: 2em; }
.prompt-editor__backdrop :deep(mark) { color: transparent; border-radius: 4px; padding: 1px 0; -webkit-box-decoration-break: clone; box-decoration-break: clone; }
.prompt-editor__backdrop :deep(mark.is-column) { background: var(--el-color-primary-light-8); box-shadow: inset 0 -1.5px 0 var(--el-color-primary-light-5); }
.prompt-editor__backdrop :deep(mark.is-code) { background: var(--zt-teal-soft); box-shadow: inset 0 -1.5px 0 var(--zt-teal-line); }
.prompt-editor__backdrop :deep(mark.is-missing), .prompt-editor__backdrop :deep(mark.is-nocode) { background: var(--zt-warning-soft); box-shadow: inset 0 -1.5px 0 var(--zt-warning); }
.prompt-editor__backdrop :deep(mark.is-pending) { background: var(--zt-soft); box-shadow: inset 0 -1.5px 0 var(--zt-border-strong); }
.prompt-editor__input { position: absolute; inset: 0; width: 100%; height: 100%; resize: none; background: transparent; color: var(--zt-ink-900); caret-color: var(--zt-blue-600); overflow: hidden; outline: none; }
.prompt-editor__input::placeholder { color: var(--zt-ink-400); }
.prompt-editor__input:focus-visible { box-shadow: inset 0 0 0 2px var(--el-color-primary-light-7); }
.prompt-editor__menu { position: absolute; z-index: 30; min-width: 220px; max-width: 380px; max-height: 260px; overflow: auto; margin: 0; padding: 4px; list-style: none; border: 1px solid var(--zt-border); border-radius: 8px; background: var(--zt-panel); box-shadow: 0 10px 28px var(--zt-shadow-float); }
.prompt-editor__menu li { display: flex; justify-content: space-between; gap: 12px; padding: 7px 10px; border-radius: 5px; font-size: 13px; cursor: pointer; }
.prompt-editor__menu li small { min-width: 0; color: var(--zt-ink-500); text-align: right; }
.prompt-editor__menu-token { flex: none; white-space: nowrap; }
.prompt-editor__menu li.is-active, .prompt-editor__menu li:hover { background: var(--el-color-primary-light-9); color: var(--zt-blue-600); }
.prompt-editor__menu .prompt-editor__menu-hint { color: var(--zt-ink-500); cursor: default; }
.prompt-editor__menu .prompt-editor__menu-hint:hover { background: none; color: var(--zt-ink-500); }
.prompt-editor__menu .prompt-editor__menu-action { color: var(--zt-blue-600); }
/* 提示词很长、往下滚时变量这一行贴在可见区域底部，随时能插。 */
.prompt-editor__vars { position: sticky; bottom: 0; z-index: 2; display: flex; align-items: center; flex-wrap: wrap; gap: 6px; padding: 10px 22px; border-top: 1px solid var(--zt-border); background: var(--zt-surface-subtle); font-size: 12px; }
.prompt-editor__vars-label { margin-right: 4px; color: var(--zt-ink-500); }
.prompt-editor__vars-hint { color: var(--zt-ink-400); }
.prompt-editor__var { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px; line-height: 18px; }
.prompt-editor__var small { font-size: 11px; opacity: 0.8; }
.prompt-editor__var.is-column { background: var(--el-color-primary-light-8); color: var(--zt-blue-700); }
.prompt-editor__var.is-code { background: var(--zt-teal-soft); color: var(--zt-teal-text); }
.prompt-editor__var.is-missing, .prompt-editor__var.is-nocode { background: var(--zt-warning-soft); color: var(--zt-warning-text); }
.prompt-editor__var.is-pending { background: var(--zt-soft); color: var(--zt-ink-500); }
.prompt-editor__vars .el-button { margin: 0; }
.prompt-editor__add { padding: 1px 8px; border: 1px dashed var(--zt-border-strong); border-radius: 999px; background: transparent; color: var(--zt-ink-500); font: inherit; line-height: 18px; cursor: pointer; }
.prompt-editor__add:hover:not(:disabled), .prompt-editor__add:focus-visible { border-color: var(--zt-blue-600); color: var(--zt-blue-600); }
.prompt-editor__add:disabled { cursor: not-allowed; opacity: 0.5; }
.prompt-editor__warn { margin-left: auto; color: var(--zt-warning-text); }
</style>
