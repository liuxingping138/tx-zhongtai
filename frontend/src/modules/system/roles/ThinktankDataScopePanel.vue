<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'

import { LEVEL_TEXT, rank, type ModuleEntry, type ModuleGroup } from '@/permissions/catalog'
import type { GrantLevel } from '@/permissions/levels'
import { levelOf, openedCount, type Grants } from '@/permissions/matrix'
import {
  applyDimensionAllMode,
  isDimensionAllMode,
  setDimensionLevel,
  syncThinktankScopesWithMenu,
  type ThinktankLibraryScope,
} from '@/permissions/thinktankScopes'
import ThinktankDimCard from './ThinktankDimCard.vue'

const props = defineProps<{
  libraries: ThinktankLibraryScope[]
  modelValue: Grants
  original: Grants
  disabled: boolean
  initialLibCode?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: Grants] }>()

const activeLibCode = ref('')
// 记录管理员手动切为「指定范围」的维度编码，避免点「指定范围」时因当前值恰好全等而跳回「全部范围」
const forcedCustom = reactive<Record<string, boolean>>({})

watch(
  [() => props.libraries, () => props.initialLibCode],
  ([libs, initialCode]) => {
    if (initialCode && libs.some(l => l.code === initialCode)) {
      activeLibCode.value = initialCode
      return
    }
    const first = libs[0]
    if (first && !libs.some(l => l.code === activeLibCode.value)) {
      activeLibCode.value = first.code
    }
  },
  { immediate: true },
)

const activeLib = computed(() => props.libraries.find(l => l.code === activeLibCode.value) ?? props.libraries[0] ?? null)
const activeMenuLevel = computed<GrantLevel>(() =>
  activeLib.value ? levelOf(props.modelValue, activeLib.value.code) : 'NONE',
)

const libMenuLevel = (code: string): GrantLevel => levelOf(props.modelValue, code)
const shortDimLabel = (name: string): string => name.replace(/范围$/, '').trim() || name

function dimMode(dim: ModuleGroup): 'ALL' | 'CUSTOM' {
  if (forcedCustom[dim.code]) return 'CUSTOM'
  return isDimensionAllMode(dim, props.modelValue, activeMenuLevel.value) ? 'ALL' : 'CUSTOM'
}

function setDimMode(dim: ModuleGroup, mode: 'ALL' | 'CUSTOM') {
  if (props.disabled) return
  if (mode === 'ALL') {
    forcedCustom[dim.code] = false
    emit('update:modelValue', applyDimensionAllMode(dim, props.modelValue, activeMenuLevel.value))
  } else {
    forcedCustom[dim.code] = true
  }
}

function quickOpenLibrary(level: Exclude<GrantLevel, 'NONE'>) {
  if (props.disabled || !activeLib.value) return
  const next = { ...props.modelValue, [activeLib.value.code]: level }
  emit('update:modelValue', syncThinktankScopesWithMenu(props.libraries, props.modelValue, next))
}

function onSetItem(item: ModuleEntry, level: GrantLevel) {
  if (props.disabled || rank(level) > rank(activeMenuLevel.value)) return
  if (level !== 'NONE' && !item.levels.includes(level)) return
  emit('update:modelValue', { ...props.modelValue, [item.code]: level })
}

function onBatchSet(dim: ModuleGroup, level: GrantLevel) {
  if (props.disabled || rank(level) > rank(activeMenuLevel.value)) return
  forcedCustom[dim.code] = true
  emit('update:modelValue', setDimensionLevel(dim, props.modelValue, level))
}
</script>

<template>
  <div class="tt-scope">
    <div
      v-if="!libraries.length"
      class="tt-scope__empty"
    >
      暂无可配置的智库子库数据权限
    </div>

    <template v-else>
      <div class="tt-overview">
        <div class="tt-overview__left">
          <span class="tt-overview__label">智库子库：</span>
          <div
            class="tt-overview__pills"
            role="tablist"
            aria-label="智库子库切换"
          >
            <button
              v-for="lib in libraries"
              :key="lib.code"
              type="button"
              role="tab"
              :aria-selected="lib.code === activeLib?.code"
              class="tt-lib-pill"
              :class="{ 'is-active': lib.code === activeLib?.code }"
              @click="activeLibCode = lib.code"
            >
              <span>{{ lib.name }}</span>
              <span
                class="tt-lib-pill__badge"
                :class="`is-${libMenuLevel(lib.code).toLowerCase()}`"
              >
                {{ LEVEL_TEXT[libMenuLevel(lib.code)] }}
              </span>
            </button>
          </div>
          <span
            v-if="activeLib && activeMenuLevel !== 'NONE'"
            class="tt-overview__counts"
          >
            <template
              v-for="(dim, idx) in activeLib.dimensions"
              :key="dim.code"
            >
              <span v-if="idx > 0">·</span>
              <span>
                {{ shortDimLabel(dim.name) }}
                <strong>{{ openedCount(dim, modelValue) }}/{{ dim.modules.length }}</strong>
              </span>
            </template>
          </span>
        </div>
        <div class="tt-overview__rule">
          <el-icon
            class="tt-overview__rule-icon"
            aria-hidden="true"
          >
            <InfoFilled />
          </el-icon>
          <span><strong>文件类型 × 行业类型取交集生效</strong>；报告库、方案库当前直接跟随菜单档位生效。</span>
        </div>
      </div>

      <div
        v-if="activeLib && activeMenuLevel === 'NONE'"
        class="tt-scope__closed"
      >
        <p class="tt-scope__closed-title">
          尚未开通「{{ activeLib.name }}」菜单访问权限
        </p>
        <p class="tt-scope__closed-desc">
          数据范围权限建立在子库菜单权限之上。请先在「菜单权限」页签开通「{{ activeLib.name }}」，或直接点击下方按钮一键开通（默认自动开启该库全部文件类型与行业范围，随后可切换至指定范围精细勾选）：
        </p>
        <div
          v-if="!disabled"
          class="tt-scope__quick-btns"
        >
          <el-button
            size="small"
            @click="quickOpenLibrary('READ')"
          >
            一键开通「仅查看」
          </el-button>
          <el-button
            size="small"
            @click="quickOpenLibrary('EXPORT')"
          >
            一键开通「查看和导出」
          </el-button>
          <el-button
            size="small"
            type="primary"
            @click="quickOpenLibrary('FULL')"
          >
            一键开通「可管理」
          </el-button>
        </div>
      </div>

      <div
        v-else-if="activeLib"
        class="tt-scope__dims"
      >
        <ThinktankDimCard
          v-for="dim in activeLib.dimensions"
          :key="dim.code"
          :library-name="activeLib.name"
          :dimension="dim"
          :menu-level="activeMenuLevel"
          :mode="dimMode(dim)"
          :grants="modelValue"
          :original="original"
          :disabled="disabled"
          @set-mode="setDimMode(dim, $event)"
          @set-item="onSetItem"
          @batch-set="onBatchSet(dim, $event)"
        />
      </div>
    </template>
  </div>
</template>

<style scoped src="./thinktank-scope.css"></style>
