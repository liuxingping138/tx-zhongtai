<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { aiTaskBilling, type AiTaskBilling, type AiTaskCode } from '@/api/aiTagging'
import { errorMessage } from '@/api/errors'
import { TASK_OUTPUT, formatYuan } from './aiTagging'

/** 一个打标任务的按天账单：每天几批、花了多少、处理了几条政策、写入多少。没跑的日子不列。 */
const props = defineProps<{ task: AiTaskCode }>()
const RANGES = [7, 30, 90]
const days = ref(30)
const billing = ref<AiTaskBilling | null>(null)
const loading = ref(false)
const error = ref('')
const output = TASK_OUTPUT[props.task]

async function load(): Promise<void> {
  loading.value = true
  try {
    billing.value = await aiTaskBilling(props.task, days.value)
    error.value = ''
  } catch (cause) {
    error.value = errorMessage(cause, '账单加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)
defineExpose({ load })
</script>

<template>
  <div v-loading="loading">
    <div class="billing__head">
      <el-radio-group
        v-model="days"
        size="small"
        aria-label="账单范围"
        @change="load"
      >
        <el-radio-button
          v-for="value in RANGES"
          :key="value"
          :value="value"
        >
          最近 {{ value }} 天
        </el-radio-button>
      </el-radio-group>
      <span v-if="billing">合计 <strong>{{ formatYuan(billing.total) }}</strong></span>
    </div>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />
    <el-table
      :data="billing?.items ?? []"
      class="data-table"
      row-key="day"
      empty-text="这段时间没有执行过"
    >
      <el-table-column
        prop="day"
        label="日期"
        width="130"
      />
      <el-table-column
        prop="runs"
        label="批次"
        width="80"
        align="right"
      />
      <el-table-column
        label="费用"
        width="120"
        align="right"
      >
        <template #default="{ row }">
          {{ formatYuan(row.cost) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="policies"
        label="处理政策"
        width="100"
        align="right"
      />
      <el-table-column
        :prop="output.key"
        :label="output.label"
        width="130"
        align="right"
      />
    </el-table>
  </div>
</template>

<style scoped>
.billing__head { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; color: var(--zt-ink-500); font-size: 13px; }
</style>
