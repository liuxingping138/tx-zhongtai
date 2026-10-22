<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { aiTaggingBilling, type AiTaggingBilling } from '@/api/aiTagging'
import { errorMessage } from '@/api/errors'
import { formatYuan } from './aiTagging'

/** 按天账单：每天几批、花了多少（拆到三步）、读了和写了多少。没跑的日子不列。 */
const RANGES = [7, 30, 90]
const days = ref(30)
const billing = ref<AiTaggingBilling | null>(null)
const loading = ref(false)
const error = ref('')

async function load(): Promise<void> {
  loading.value = true
  try {
    billing.value = await aiTaggingBilling(days.value)
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
      <span v-if="billing">
        合计 <strong>{{ formatYuan(billing.total.cost) }}</strong>：类型判断 {{ formatYuan(billing.total.type_cost) }} ·
        政策解读 {{ formatYuan(billing.total.interpret_cost) }} · 市场机会 {{ formatYuan(billing.total.opportunity_cost) }}
      </span>
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
        width="120"
      />
      <el-table-column
        prop="runs"
        label="批次"
        width="70"
        align="right"
      />
      <el-table-column
        v-for="column in [
          { prop: 'cost', label: '费用' },
          { prop: 'type_cost', label: '类型判断' },
          { prop: 'interpret_cost', label: '政策解读' },
          { prop: 'opportunity_cost', label: '市场机会' },
        ]"
        :key="column.prop"
        :label="column.label"
        width="110"
        align="right"
      >
        <template #default="{ row }">
          {{ formatYuan(row[column.prop]) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="source_rows"
        label="读取"
        width="80"
        align="right"
      />
      <el-table-column
        prop="tagged_rows"
        label="写入标签"
        width="90"
        align="right"
      />
      <el-table-column
        prop="interpret_rows"
        label="解读行"
        width="80"
        align="right"
      />
    </el-table>
  </div>
</template>

<style scoped>
.billing__head { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; color: var(--zt-ink-500); font-size: 13px; }
</style>
