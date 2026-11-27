<script setup lang="ts">
import { isChecked, supports, type ModuleEntry } from '@/permissions/catalog'
import type { GrantLevel } from '@/permissions/levels'
import { COLUMNS, type Column } from '@/permissions/matrix'

/** 矩阵里一个菜单的「查看 / 导出 / 管理」三个整格热区；没有的操作显示浅灰破折号。 */
defineProps<{ module: ModuleEntry; level: GrantLevel; disabled: boolean }>()
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
      v-if="supports(module, column.level)"
      class="perm-cell"
      :class="{ 'is-disabled': disabled }"
      :title="`${module.name} · ${column.label}（${column.what}）`"
      @mouseenter="$emit('hoverCol', column.level)"
      @mouseleave="$emit('hoverCol', null)"
    >
      <input
        type="checkbox"
        :aria-label="`${module.name} ${column.label}`"
        :checked="isChecked(level, column.level)"
        :disabled="disabled"
        @change="$emit('toggle', column.level)"
      >
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
