<script setup lang="ts">
import { STATUSES } from './candidates'

/** 新增场景审核的页签：待审、已采纳、已合并、已驳回各有几个，能看码表的再多一个「补充待确认」。 */
defineProps<{ value: string; counts: Record<string, number>; enrichTab: string; enrichCount: number }>()
const emit = defineEmits<{ change: [value: string | number | boolean | undefined] }>()
</script>

<template>
  <el-radio-group
    :model-value="value"
    aria-label="按状态看"
    @update:model-value="emit('change', $event)"
  >
    <el-radio-button
      v-for="status in STATUSES"
      :key="status"
      :value="status"
    >
      {{ status }} {{ (counts[status] ?? 0).toLocaleString() }}
    </el-radio-button>
    <el-radio-button
      v-if="enrichTab"
      :value="enrichTab"
    >
      {{ enrichTab }} {{ enrichCount.toLocaleString() }}
    </el-radio-button>
  </el-radio-group>
</template>
