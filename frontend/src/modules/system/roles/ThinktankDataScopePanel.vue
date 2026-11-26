<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { LEVEL_TEXT, type ModuleGroup } from '@/permissions/catalog'
import type { GrantLevel } from '@/permissions/levels'
import { levelOf, openedCount, type Grants } from '@/permissions/matrix'
import {
  applyDimensionAllMode,
  capDimensionToMenuLevel,
  isDimensionAllMode,
  syncThinktankScopesWithMenu,
  type ThinktankLibraryScope,
} from '@/permissions/thinktankScopes'
import PermissionTable from './PermissionTable.vue'

const props = defineProps<{
  libraries: ThinktankLibraryScope[]
  modelValue: Grants
  original: Grants
  disabled: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: Grants] }>()

const activeLibCode = ref('')
// 记录管理员手动展开为「指定范围」的维度编码，避免点「指定范围」时因当前值恰好全等而跳回「全部范围」
const forcedCustom = reactive<Record<string, boolean>>({})

watch(
  () => props.libraries,
  libs => {
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

function libMenuLevel(code: string): GrantLevel {
  return levelOf(props.modelValue, code)
}

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

function onDimensionGrantsUpdate(next: Grants) {
  emit('update:modelValue', next)
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
      <div class="tt-scope__libs">
        <span class="tt-scope__libs-label">智库子库：</span>
        <div
          class="tt-scope__lib-pills"
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
            <span class="tt-lib-pill__name">{{ lib.name }}</span>
            <span
              class="tt-lib-pill__badge"
              :class="`is-${libMenuLevel(lib.code).toLowerCase()}`"
            >
              {{ LEVEL_TEXT[libMenuLevel(lib.code)] }}
            </span>
          </button>
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
          数据范围权限建立在子库菜单权限之上。请先在「菜单权限」页签开通「{{ activeLib.name }}」，或直接点击下方按钮一键开通（默认自动开启该库全部文件类型与行业范围）：
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
        <section
          v-for="dim in activeLib.dimensions"
          :key="dim.code"
          class="tt-dim-card"
        >
          <header class="tt-dim-card__head">
            <div class="tt-dim-card__info">
              <h3 class="tt-dim-card__title">
                {{ activeLib.name }} · {{ dim.name }}
              </h3>
              <span class="tt-dim-card__meta">
                <template v-if="dimMode(dim) === 'ALL'">
                  全部 {{ dim.modules.length }} 项均已开通（{{ LEVEL_TEXT[activeMenuLevel] }}）
                </template>
                <template v-else>
                  已开通 {{ openedCount(dim, modelValue) }} / {{ dim.modules.length }} 项
                </template>
              </span>
            </div>

            <div
              class="tt-dim-card__switch"
              role="radiogroup"
              :aria-label="`${dim.name}授权模式`"
            >
              <button
                type="button"
                class="tt-mode-btn"
                :class="{ 'is-active': dimMode(dim) === 'ALL' }"
                :disabled="disabled"
                @click="setDimMode(dim, 'ALL')"
              >
                全部范围（跟随菜单档位）
              </button>
              <button
                type="button"
                class="tt-mode-btn"
                :class="{ 'is-active': dimMode(dim) === 'CUSTOM' }"
                :disabled="disabled"
                @click="setDimMode(dim, 'CUSTOM')"
              >
                指定范围（按项勾选）
              </button>
            </div>
          </header>

          <div
            v-if="dimMode(dim) === 'ALL'"
            class="tt-dim-card__all-body"
          >
            <p class="tt-dim-card__all-hint">
              当前不限制此维度，全部 {{ dim.modules.length }} 个分类均按「{{ activeLib.name }}」菜单档位（<b>{{ LEVEL_TEXT[activeMenuLevel] }}</b>）放行。如需仅开放部分分类或设置不同档位，请切换至「指定范围」。
            </p>
            <div class="tt-dim-card__tags">
              <span
                v-for="item in dim.modules"
                :key="item.code"
                class="tt-dim-tag"
              >
                {{ item.name }}
              </span>
            </div>
          </div>

          <div
            v-else
            class="tt-dim-card__custom-body"
          >
            <PermissionTable
              :model-value="modelValue"
              :groups="[capDimensionToMenuLevel(dim, activeMenuLevel)]"
              :original="original"
              :disabled="disabled"
              @update:model-value="onDimensionGrantsUpdate"
            />
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.tt-scope { display: flex; flex-direction: column; gap: 16px; }
.tt-scope__empty { padding: 32px 16px; text-align: center; color: var(--zt-ink-500); border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); }
.tt-scope__libs { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; padding: 12px 16px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-surface-subtle); }
.tt-scope__libs-label { font-size: 13px; font-weight: 600; color: var(--zt-ink-700); }
.tt-scope__lib-pills { display: flex; flex-wrap: wrap; gap: 8px; }
.tt-lib-pill { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; border: 1px solid var(--zt-border); border-radius: 6px; background: var(--zt-panel); color: var(--zt-ink-700); font-size: 13px; cursor: pointer; transition: border-color 0.15s, background-color 0.15s; }
.tt-lib-pill.is-active { border-color: var(--zt-blue-600); background: var(--el-color-primary-light-9); color: var(--zt-ink-900); font-weight: 600; }
.tt-lib-pill__badge { padding: 2px 6px; border-radius: 4px; font-size: 11.5px; font-weight: 500; background: var(--zt-soft); color: var(--zt-ink-500); }
.tt-lib-pill__badge.is-read, .tt-lib-pill__badge.is-export, .tt-lib-pill__badge.is-full { background: var(--zt-blue-600); color: var(--zt-on-primary); }
.tt-scope__closed { padding: 28px 24px; border: 1px dashed var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-surface-subtle); }
.tt-scope__closed-title { margin: 0 0 6px; font-size: 15px; font-weight: 600; color: var(--zt-ink-900); }
.tt-scope__closed-desc { margin: 0 0 14px; font-size: 13px; line-height: 1.6; color: var(--zt-ink-700); }
.tt-scope__quick-btns { display: flex; flex-wrap: wrap; gap: 8px; }
.tt-scope__dims { display: flex; flex-direction: column; gap: 16px; }
.tt-dim-card { border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); overflow: hidden; }
.tt-dim-card__head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; padding: 12px 16px; background: var(--zt-surface-subtle); border-bottom: 1px solid var(--zt-divider); }
.tt-dim-card__info { display: flex; align-items: baseline; flex-wrap: wrap; gap: 10px; }
.tt-dim-card__title { margin: 0; font-size: 14px; font-weight: 650; color: var(--zt-ink-900); }
.tt-dim-card__meta { font-size: 12px; color: var(--zt-ink-500); font-variant-numeric: tabular-nums; }
.tt-dim-card__switch { display: inline-flex; padding: 2px; border: 1px solid var(--zt-border); border-radius: 6px; background: var(--zt-panel); }
.tt-mode-btn { padding: 4px 10px; border: 0; border-radius: 4px; background: transparent; font-size: 12px; color: var(--zt-ink-700); cursor: pointer; }
.tt-mode-btn.is-active { background: var(--zt-blue-600); color: var(--zt-on-primary); font-weight: 600; }
.tt-mode-btn:disabled { cursor: not-allowed; opacity: 0.6; }
.tt-dim-card__all-body { padding: 14px 16px; }
.tt-dim-card__all-hint { margin: 0 0 10px; font-size: 12.5px; color: var(--zt-ink-700); line-height: 1.6; }
.tt-dim-card__tags { display: flex; flex-wrap: wrap; gap: 6px; }
.tt-dim-tag { padding: 3px 9px; border-radius: 4px; background: var(--zt-soft); border: 1px solid var(--zt-divider); font-size: 12px; color: var(--zt-ink-700); }
.tt-dim-card__custom-body :deep(.perm-menu) { border: 0; border-radius: 0; }
</style>
