<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'

import { LEVEL_TEXT, rank, type ModuleEntry, type ModuleGroup } from '@/permissions/catalog'
import type { GrantLevel } from '@/permissions/levels'
import { isChanged, levelOf, openedCount, type Grants } from '@/permissions/matrix'
import { countDimensionChanges } from '@/permissions/thinktankScopes'

const LEVEL_OPTIONS: { level: GrantLevel; short: string; label: string }[] = [
  { level: 'NONE', short: '无', label: '无权限' },
  { level: 'READ', short: '查', label: '仅查看' },
  { level: 'EXPORT', short: '导', label: '查看和导出' },
  { level: 'FULL', short: '管', label: '可管理' },
]

const props = defineProps<{
  libraryName: string
  dimension: ModuleGroup
  menuLevel: GrantLevel
  mode: 'ALL' | 'CUSTOM'
  grants: Grants
  original: Grants
  disabled: boolean
}>()

const emit = defineEmits<{
  setMode: [mode: 'ALL' | 'CUSTOM']
  setItem: [item: ModuleEntry, level: GrantLevel]
  batchSet: [level: GrantLevel]
}>()

const keyword = ref('')
const onlyChanged = ref(false)

const shortLabel = computed(() => props.dimension.name.replace(/范围$/, '').trim() || props.dimension.name)
const opened = computed(() => openedCount(props.dimension, props.grants))
const changesCount = computed(() => countDimensionChanges(props.dimension, props.grants, props.original))

const filteredItems = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return props.dimension.modules.filter(item => {
    if (query && !item.name.toLowerCase().includes(query)) return false
    if (onlyChanged.value && !isChanged(props.grants, props.original, item.code)) return false
    return true
  })
})

function isBlocked(item: ModuleEntry, level: GrantLevel): boolean {
  if (rank(level) > rank(props.menuLevel)) return true
  return level !== 'NONE' && !item.levels.includes(level)
}

function levelTitle(item: ModuleEntry, option: { level: GrantLevel; label: string }): string {
  if (rank(option.level) > rank(props.menuLevel)) {
    return `不可高于「${props.libraryName}」菜单档位（${LEVEL_TEXT[props.menuLevel]}）`
  }
  if (option.level !== 'NONE' && !item.levels.includes(option.level)) {
    return `${item.name}不支持「${option.label}」`
  }
  return `${item.name}：${option.label}`
}
</script>

<template>
  <section class="tt-dim-card">
    <header class="tt-dim-card__head">
      <div class="tt-dim-card__info">
        <h3 class="tt-dim-card__title">
          {{ libraryName }} · {{ dimension.name }}
        </h3>
        <span class="tt-dim-card__meta">
          <template v-if="mode === 'ALL'">
            全部 {{ dimension.modules.length }} 项均已开通（{{ LEVEL_TEXT[menuLevel] }}）
          </template>
          <template v-else>
            已开通 {{ opened }} / {{ dimension.modules.length }} 项
          </template>
          <span
            v-if="changesCount > 0"
            class="tt-dim-card__meta-dirty"
          >
            · 本维度修改 {{ changesCount }} 项
          </span>
        </span>
      </div>

      <div
        class="tt-dim-card__switch"
        role="radiogroup"
        :aria-label="`${dimension.name}授权模式`"
      >
        <button
          type="button"
          class="tt-mode-btn"
          :class="{ 'is-active': mode === 'ALL' }"
          :disabled="disabled"
          @click="emit('setMode', 'ALL')"
        >
          全部范围（跟随菜单）
        </button>
        <button
          type="button"
          class="tt-mode-btn"
          :class="{ 'is-active': mode === 'CUSTOM' }"
          :disabled="disabled"
          @click="emit('setMode', 'CUSTOM')"
        >
          指定范围（分级勾选）
        </button>
      </div>
    </header>

    <div
      v-if="mode === 'ALL'"
      class="tt-dim-card__all-body"
    >
      <p class="tt-dim-card__all-hint">
        当前不限制此维度，全部 {{ dimension.modules.length }} 个分类均按「{{ libraryName }}」菜单档位（<b>{{ LEVEL_TEXT[menuLevel] }}</b>）放行。如需仅开放部分分类或设置不同档位，请切换至「指定范围」。
      </p>
      <div class="tt-dim-card__tags">
        <span
          v-for="item in dimension.modules"
          :key="item.code"
          class="tt-dim-tag"
        >
          <span
            class="tt-dim-tag__dot"
            aria-hidden="true"
          />
          {{ item.name }}
        </span>
      </div>
    </div>

    <div
      v-else
      class="tt-dim-card__custom-body"
    >
      <div class="tt-custom-bar">
        <div class="tt-custom-bar__left">
          <el-input
            v-model="keyword"
            clearable
            size="small"
            :placeholder="`搜索${shortLabel}`"
            :aria-label="`搜索${shortLabel}`"
            class="tt-dim-search"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <button
            v-if="changesCount > 0"
            type="button"
            class="tt-dirty-toggle"
            :class="{ 'is-active': onlyChanged }"
            @click="onlyChanged = !onlyChanged"
          >
            仅看已修改 ({{ changesCount }})
          </button>
        </div>
        <div class="tt-batch-bar">
          <span>批量设为：</span>
          <button
            v-for="opt in LEVEL_OPTIONS"
            :key="opt.level"
            type="button"
            class="tt-batch-btn"
            :disabled="disabled || rank(opt.level) > rank(menuLevel)"
            :title="rank(opt.level) > rank(menuLevel) ? `不可高于子库菜单档位（${LEVEL_TEXT[menuLevel]}）` : `将${dimension.name}全部项设为${opt.label}`"
            @click="emit('batchSet', opt.level)"
          >
            {{ opt.level === 'NONE' ? '全部清空' : opt.label }}
          </button>
        </div>
      </div>

      <div class="tt-grid">
        <p
          v-if="!filteredItems.length"
          class="tt-grid__empty"
        >
          没有匹配的分类项
        </p>
        <div
          v-for="item in filteredItems"
          :key="item.code"
          class="tt-item-card"
          :class="[
            `is-${levelOf(grants, item.code).toLowerCase()}`,
            { 'is-changed': isChanged(grants, original, item.code) },
          ]"
        >
          <div
            class="tt-item-card__name"
            :title="item.name"
          >
            <span
              v-if="isChanged(grants, original, item.code)"
              class="tt-item-card__dot"
              title="已修改"
            />
            <span class="tt-item-card__text">{{ item.name }}</span>
          </div>
          <div
            class="tt-seg"
            role="radiogroup"
            :aria-label="`${item.name}权限档位`"
          >
            <button
              v-for="opt in LEVEL_OPTIONS"
              :key="opt.level"
              type="button"
              role="radio"
              :aria-checked="levelOf(grants, item.code) === opt.level"
              :aria-label="`${item.name} ${opt.label}`"
              class="tt-seg__btn"
              :class="[
                `is-${opt.level.toLowerCase()}`,
                { 'is-active': levelOf(grants, item.code) === opt.level },
              ]"
              :disabled="disabled || isBlocked(item, opt.level)"
              :title="levelTitle(item, opt)"
              @click="emit('setItem', item, opt.level)"
            >
              {{ opt.short }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped src="./thinktank-scope.css"></style>
