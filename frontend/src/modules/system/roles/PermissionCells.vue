<script setup lang="ts">
import type { ModuleEntry } from '@/permissions/catalog'
import { COLUMNS, isColumnChecked, supportsColumn, type Column, type Grants } from '@/permissions/matrix'

/** 矩阵里一个菜单的「查看 / 下载 / 导出 / 管理」四个整格热区；采用 Material 3 定制矢量复选框。 */
defineProps<{ module: ModuleEntry; grants: Grants; disabled: boolean }>()
defineEmits<{
  toggle: [column: Column]
  hoverCol: [column: Column | null]
}>()
</script>

<template>
  <template
    v-for="column in COLUMNS"
    :key="column.level"
  >
    <label
      v-if="supportsColumn(module, column.level)"
      class="perm-cell"
      :class="{
        'is-disabled': disabled,
        'is-checked': isColumnChecked(module, column.level, grants),
        'is-download': column.level === 'DOWNLOAD',
      }"
      :title="`${module.name} · ${column.label}（${column.what}）`"
      @mouseenter="$emit('hoverCol', column.level)"
      @mouseleave="$emit('hoverCol', null)"
    >
      <span class="m3-check-wrap">
        <input
          type="checkbox"
          class="m3-check"
          :aria-label="`${module.name} ${column.label}`"
          :checked="isColumnChecked(module, column.level, grants)"
          :disabled="disabled"
          @change="$emit('toggle', column.level)"
        >
      </span>
    </label>
    <div
      v-else
      class="perm-cell is-na"
      title="这个菜单没有这项操作"
      @mouseenter="$emit('hoverCol', column.level)"
      @mouseleave="$emit('hoverCol', null)"
    >
      <span class="perm-matrix__na">—</span>
    </div>
  </template>
</template>
