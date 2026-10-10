<script setup lang="ts">
import { isChecked, supports, type ModuleEntry } from '@/permissions/catalog'
import type { GrantLevel } from '@/permissions/levels'
import { COLUMNS, type Column } from '@/permissions/matrix'

/** 矩阵里一个菜单的「查看 / 导出 / 管理」三个格子；菜单没有的操作显示浅灰破折号。 */
defineProps<{ module: ModuleEntry; level: GrantLevel; disabled: boolean }>()
defineEmits<{ toggle: [column: Column] }>()
</script>

<template>
  <td
    v-for="column in COLUMNS"
    :key="column.level"
    class="perm-matrix__col"
  >
    <input
      v-if="supports(module, column.level)"
      type="checkbox"
      :aria-label="`${module.name} ${column.label}`"
      :checked="isChecked(level, column.level)"
      :disabled="disabled"
      @change="$emit('toggle', column.level)"
    >
    <span
      v-else
      class="perm-matrix__na"
      title="这个菜单没有这项操作"
    >—</span>
  </td>
</template>
