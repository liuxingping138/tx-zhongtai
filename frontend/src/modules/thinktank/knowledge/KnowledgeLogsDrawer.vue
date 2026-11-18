<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { ref, watch } from 'vue'

import { errorMessage } from '@/api/errors'
import { listKnowledgeLogs, type KnowledgeOpLogItem } from '@/api/thinktank'

const props = defineProps<{
  modelValue: boolean
  fileId: string
  fileName: string
}>()

defineEmits<{ 'update:modelValue': [value: boolean] }>()

const logs = ref<KnowledgeOpLogItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 15
const loading = ref(false)

async function fetchLogs() {
  if (!props.fileId) return
  loading.value = true
  try {
    const res = await listKnowledgeLogs(props.fileId, { page: page.value, page_size: pageSize })
    logs.value = res.items
    total.value = res.total
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载文件操作日志失败'))
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.modelValue, props.fileId],
  ([open]) => {
    if (open) {
      page.value = 1
      void fetchLogs()
    }
  },
)
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    :title="`操作日志 · ${fileName || ''}`"
    size="520px"
    destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div
      v-loading="loading"
      class="logs-body"
    >
      <el-empty
        v-if="!loading && logs.length === 0"
        description="暂无操作日志"
      />
      <el-timeline v-else>
        <el-timeline-item
          v-for="item in logs"
          :key="item.id"
          :timestamp="item.created_at"
          placement="top"
        >
          <div class="log-head">
            <el-tag size="small">
              {{ item.op_type }}
            </el-tag>
            <span class="log-actor">{{ item.actor_name }}</span>
          </div>
          <div class="log-detail">
            {{ item.detail }}
          </div>
        </el-timeline-item>
      </el-timeline>
      <div
        v-if="total > pageSize"
        class="logs-pager"
      >
        <el-pagination
          v-model:current-page="page"
          layout="prev, pager, next"
          :page-size="pageSize"
          :total="total"
          @current-change="fetchLogs"
        />
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.logs-body { min-height: 200px; }
.log-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.log-actor { font-weight: 500; color: var(--zt-ink-900); }
.log-detail { font-size: 13px; color: var(--zt-ink-500); }
.logs-pager { display: flex; justify-content: flex-end; margin-top: 12px; }
</style>
