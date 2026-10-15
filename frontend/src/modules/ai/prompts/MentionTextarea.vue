<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'

import { insertMention, mentionAt, mentionOptions } from '../shared/aiText'

const props = defineProps<{ headers: string[]; hasCode: boolean; label: string }>()
const text = defineModel<string>({ required: true })
const input = ref<{ textarea?: HTMLTextAreaElement } | null>(null)
const trigger = ref<{ at: number; keyword: string } | null>(null)
const active = ref(0)
const options = computed(() => (trigger.value ? mentionOptions(props.headers, props.hasCode, trigger.value.keyword) : []))
const open = computed(() => trigger.value !== null)

function element(): HTMLTextAreaElement | undefined {
  return input.value?.textarea
}

function detect(): void {
  const area = element()
  trigger.value = area ? mentionAt(area.value, area.selectionStart) : null
  active.value = 0
}

async function choose(field: string): Promise<void> {
  const area = element()
  if (!area || !trigger.value) return
  const next = insertMention(area.value, trigger.value.at, area.selectionStart, field)
  text.value = next.text
  trigger.value = null
  await nextTick()
  area.focus()
  area.setSelectionRange(next.caret, next.caret)
}

function move(step: number): void {
  const count = options.value.length
  active.value = (active.value + step + count) % count
}

const KEY_ACTIONS: Record<string, () => void> = {
  ArrowDown: () => move(1),
  ArrowUp: () => move(-1),
  Enter: () => void choose(options.value[active.value] ?? ''),
  Tab: () => void choose(options.value[active.value] ?? ''),
}

function onKeydown(event: KeyboardEvent): void {
  if (!open.value || event.isComposing) return
  if (event.key === 'Escape') {
    trigger.value = null
    event.preventDefault()
    return
  }
  const action = KEY_ACTIONS[event.key]
  if (action && options.value.length) {
    action()
    event.preventDefault()
  }
}
</script>

<template>
  <div class="mention">
    <el-input
      ref="input"
      v-model="text"
      type="textarea"
      :autosize="{ minRows: 8, maxRows: 18 }"
      resize="vertical"
      :aria-label="label"
      placeholder="输入提示词。输入 @ 选择 Excel 列名插入变量，提问时替换为该行的值"
      @input="detect"
      @click="detect"
      @keydown="onKeydown"
      @blur="trigger = null"
    />
    <ul
      v-if="open"
      class="mention__list"
      role="listbox"
      aria-label="可插入的变量"
    >
      <li
        v-if="!options.length"
        class="mention__hint"
      >
        {{ headers.length || hasCode ? '没有匹配的列名' : '先上传 Excel 或码表，才能插入变量' }}
      </li>
      <li
        v-for="(option, index) in options"
        :key="option"
        role="option"
        :aria-selected="index === active"
        :class="{ 'is-active': index === active }"
        @mousedown.prevent="choose(option)"
      >
        @【{{ option }}】
      </li>
    </ul>
  </div>
</template>

<style scoped>
.mention { position: relative; }
.mention__list { position: absolute; z-index: 20; left: 0; top: calc(100% + 4px); min-width: 220px; max-width: 340px; max-height: 240px; overflow: auto; margin: 0; padding: 4px; list-style: none; border: 1px solid var(--zt-border); border-radius: 6px; background: var(--zt-panel); box-shadow: 0 6px 18px rgb(22 38 56 / 12%); }
.mention__list li { padding: 7px 10px; border-radius: 4px; font-size: 13px; cursor: pointer; }
.mention__list li.is-active, .mention__list li:hover { background: var(--el-color-primary-light-9); color: var(--zt-blue-600); }
.mention__list .mention__hint { color: var(--zt-ink-500); cursor: default; }
.mention__list .mention__hint:hover { background: none; color: var(--zt-ink-500); }
</style>
