<script setup lang="ts">
import { computed, h, nextTick, ref, type FunctionalComponent } from 'vue'

import { CODE_TABLE_FIELD, insertMention, mentionAt, mentionOptions } from '../shared/aiText'
import { promptSegments, unusedColumns, usedVariables, type PromptSegment, type VariableState } from './promptVariables'

/**
 * 写提示词的编辑器：@【列名】在文字底下直接画成标记——能替换的蓝色、码表青色、Excel 里找不到的琥珀色，
 * 写错列名不用等试发就能看出来。输入 @ 在光标处弹出列名；Ctrl/⌘ + Enter 试发，Ctrl/⌘ + S 保存。
 *
 * 做法是常见的「背景层 + 透明 textarea」：背景层和 textarea 同字体、同内边距、同换行规则，
 * 文字透明只画标记底色，textarea 在上面负责输入和光标，滚动时同步背景层。
 */
// 背景层逐段输出文字和标记。用渲染函数而不是模板：模板里标签之间的换行会被压成空格，背景层就和输入框错位了。
// 渲染函数生成的 mark 不带本组件的作用域标识，样式里要用 :deep(mark)。
const MirrorText: FunctionalComponent<{ parts: PromptSegment[] }> = ({ parts }) =>
  parts.map(part => (part.state ? h('mark', { class: `is-${part.state}` }, part.text) : part.text))
MirrorText.props = ['parts']

const props = withDefaults(defineProps<{ headers: string[]; hasCode: boolean; disabled?: boolean }>(), { disabled: false })
const emit = defineEmits<{ run: []; save: [] }>()
const text = defineModel<string>({ required: true })

const area = ref<HTMLTextAreaElement | null>(null)
const backdrop = ref<HTMLElement | null>(null)
const caretMark = ref<HTMLElement | null>(null)
const trigger = ref<{ at: number; keyword: string; caret: number } | null>(null)
const active = ref(0)
const popup = ref({ top: 0, left: 0 })

const options = computed(() => (trigger.value ? mentionOptions(props.headers, props.hasCode, trigger.value.keyword) : []))
const before = computed(() => promptSegments(trigger.value ? text.value.slice(0, trigger.value.caret) : text.value, props.headers, props.hasCode))
const after = computed(() => (trigger.value ? promptSegments(text.value.slice(trigger.value.caret), props.headers, props.hasCode) : []))
const used = computed(() => usedVariables(text.value, props.headers, props.hasCode))
const candidates = computed(() => unusedColumns(text.value, props.headers))
const missing = computed(() => used.value.filter(item => item.state === 'missing').length)
const STATE_TEXT: Record<VariableState, string> = { column: 'Excel 列', code: '码表全文', missing: '找不到' }

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
  if (mark) popup.value = { top: mark.offsetTop - element.scrollTop + 24, left: Math.min(mark.offsetLeft, element.clientWidth - 260) }
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
        placeholder="写下要让模型做的事。输入 @ 插入 Excel 列名，批量提问时逐行替换成该行的值；@【上传码表】替换成码表全文。"
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
          v-if="!options.length"
          class="prompt-editor__menu-hint"
        >
          {{ headers.length || hasCode ? '没有匹配的列名' : '先上传 Excel 或选码表，才有变量可插' }}
        </li>
        <li
          v-for="(option, index) in options"
          :key="option"
          role="option"
          :aria-selected="index === active"
          :class="{ 'is-active': index === active }"
          @mousedown.prevent="choose(option)"
        >
          @【{{ option }}】<small v-if="option === CODE_TABLE_FIELD">码表全文</small>
        </li>
      </ul>
    </div>
    <div
      class="prompt-editor__vars"
      aria-label="提示词里的变量"
    >
      <span class="prompt-editor__vars-label">变量</span>
      <span
        v-if="!used.length && !candidates.length"
        class="prompt-editor__vars-hint"
      >上传 Excel 后，这里列出可插入的列名</span>
      <span
        v-for="item in used"
        :key="item.name"
        class="prompt-editor__var"
        :class="`is-${item.state}`"
        :title="item.state === 'missing' ? 'Excel 里没有这一列，提问时会原样留在提示词里' : STATE_TEXT[item.state]"
      >{{ item.name }}<small>{{ item.state === 'missing' ? '找不到' : item.count > 1 ? `×${item.count}` : '' }}</small></span>
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
      <span
        v-if="missing"
        class="prompt-editor__warn"
        role="status"
      >{{ missing }} 个变量在 Excel 里找不到</span>
    </div>
  </div>
</template>

<style scoped>
.prompt-editor { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.prompt-editor__surface { position: relative; flex: 1; min-height: 260px; }
.prompt-editor__backdrop, .prompt-editor__input {
  position: absolute; inset: 0; margin: 0; padding: 18px 22px; border: 0;
  font: 14px/1.85 var(--zt-font); letter-spacing: 0.01em; white-space: pre-wrap; overflow-wrap: anywhere; word-break: normal;
}
.prompt-editor__backdrop { overflow: hidden; pointer-events: none; color: transparent; }
.prompt-editor__mirror { min-height: 100%; padding-bottom: 2em; }
.prompt-editor__backdrop :deep(mark) { color: transparent; border-radius: 4px; padding: 1px 0; -webkit-box-decoration-break: clone; box-decoration-break: clone; }
.prompt-editor__backdrop :deep(mark.is-column) { background: #e3eefc; box-shadow: inset 0 -1.5px 0 #9bbcea; }
.prompt-editor__backdrop :deep(mark.is-code) { background: #dcf1ee; box-shadow: inset 0 -1.5px 0 #82c3b8; }
.prompt-editor__backdrop :deep(mark.is-missing) { background: #fbecd6; box-shadow: inset 0 -1.5px 0 #d7a45c; }
.prompt-editor__input { width: 100%; height: 100%; resize: none; background: transparent; color: var(--zt-ink-900); caret-color: var(--zt-blue-600); overflow: auto; outline: none; }
.prompt-editor__input::placeholder { color: #9aa6b6; }
.prompt-editor__input:focus-visible { box-shadow: inset 0 0 0 2px var(--el-color-primary-light-7); }
.prompt-editor__menu { position: absolute; z-index: 30; min-width: 220px; max-width: 320px; max-height: 260px; overflow: auto; margin: 0; padding: 4px; list-style: none; border: 1px solid var(--zt-border); border-radius: 8px; background: var(--zt-panel); box-shadow: 0 10px 28px rgb(22 38 56 / 14%); }
.prompt-editor__menu li { display: flex; justify-content: space-between; gap: 12px; padding: 7px 10px; border-radius: 5px; font-size: 13px; cursor: pointer; }
.prompt-editor__menu li small { color: var(--zt-ink-500); }
.prompt-editor__menu li.is-active, .prompt-editor__menu li:hover { background: var(--el-color-primary-light-9); color: var(--zt-blue-600); }
.prompt-editor__menu .prompt-editor__menu-hint { color: var(--zt-ink-500); cursor: default; }
.prompt-editor__menu .prompt-editor__menu-hint:hover { background: none; color: var(--zt-ink-500); }
.prompt-editor__vars { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; padding: 10px 22px; border-top: 1px solid var(--zt-border); background: #fafbfd; font-size: 12px; }
.prompt-editor__vars-label { margin-right: 4px; color: var(--zt-ink-500); }
.prompt-editor__vars-hint { color: #9aa6b6; }
.prompt-editor__var { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px; line-height: 18px; }
.prompt-editor__var small { font-size: 11px; opacity: 0.8; }
.prompt-editor__var.is-column { background: #e3eefc; color: #2362c5; }
.prompt-editor__var.is-code { background: #dcf1ee; color: #1f7a6b; }
.prompt-editor__var.is-missing { background: #fbecd6; color: #9a5b12; }
.prompt-editor__add { padding: 1px 8px; border: 1px dashed #c9d4e2; border-radius: 999px; background: transparent; color: var(--zt-ink-500); font: inherit; line-height: 18px; cursor: pointer; }
.prompt-editor__add:hover:not(:disabled), .prompt-editor__add:focus-visible { border-color: var(--zt-blue-600); color: var(--zt-blue-600); }
.prompt-editor__add:disabled { cursor: not-allowed; opacity: 0.5; }
.prompt-editor__warn { margin-left: auto; color: #9a5b12; }
</style>
