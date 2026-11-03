<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'

/** 表格行末的「查看」「编辑」：查看描边、编辑浅底主色，两个一样高。有独立详情页的跳过去，否则交给列表开抽屉。 */
defineProps<{ view?: RouteLocationRaw; edit?: RouteLocationRaw; canEdit: boolean }>()
const emit = defineEmits<{ view: []; edit: [] }>()
</script>

<template>
  <div class="row-actions">
    <RouterLink
      v-if="view"
      class="row-action"
      :to="view"
    >
      查看
    </RouterLink>
    <button
      v-else
      type="button"
      class="row-action"
      @click="emit('view')"
    >
      查看
    </button>
    <template v-if="canEdit">
      <RouterLink
        v-if="edit"
        class="row-action row-action--primary"
        :to="edit"
      >
        编辑
      </RouterLink>
      <button
        v-else
        type="button"
        class="row-action row-action--primary"
        @click="emit('edit')"
      >
        编辑
      </button>
    </template>
  </div>
</template>

<style scoped>
.row-actions { display: flex; gap: 8px; }
.row-action { display: inline-flex; align-items: center; justify-content: center; height: 26px; padding: 0 11px; border: 1px solid var(--zt-border-strong); border-radius: 4px; background: var(--zt-panel); color: var(--zt-ink-700); font: inherit; font-size: 13px; line-height: 1; text-decoration: none; cursor: pointer; transition: border-color .15s, color .15s, background-color .15s; }
.row-action:hover { border-color: var(--zt-blue-600); color: var(--zt-blue-600); }
.row-action--primary { border-color: transparent; background: var(--el-color-primary-light-9); color: var(--zt-blue-700); }
.row-action--primary:hover { border-color: transparent; background: var(--el-color-primary-light-8); color: var(--zt-blue-800); }
.row-action:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 1px; }
@media (prefers-reduced-motion: reduce) { .row-action { transition: none; } }
</style>
