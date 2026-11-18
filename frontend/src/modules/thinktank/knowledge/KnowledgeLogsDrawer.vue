<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { ref, watch } from 'vue'

import { errorMessage } from '@/api/errors'
import { listKnowledgeLogs, type KnowledgeOpLogItem } from '@/api/thinktank'
import ParagraphSkeleton from '@/components/ParagraphSkeleton.vue'

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
    <div class="logs-body">
      <ParagraphSkeleton
        v-if="loading"
        :lines="6"
      />
      <el-empty
        v-else-if="logs.length === 0"
        description="暂无操作日志"
      />
      <el-timeline v-else>
        <el-timeline-item
          v-for="item in logs"
          :key="item.id"
          :timestamp="item.created_at"
          placement="top"
        >
          <div class="log-card">
            <div class="log-head">
              <el-tag size="small">
                {{ item.op_type }}
              </el-tag>
              <span class="log-actor">{{ item.actor_name }}</span>
            </div>
            <div
              v-if="item.detail"
              class="log-detail"
            >
              {{ item.detail }}
            </div>
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
.logs-body { min-height: 200px; padding: 4px 8px; }
.log-card { padding: 12px 16px; background: var(--zt-soft); border: 1px solid var(--zt-border); border-radius: 8px; }
.log-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.log-actor { font-weight: 600; font-size: 13px; color: var(--zt-ink-900); }
.log-detail { color: var(--zt-ink-700); font-size: 13px; line-height: 1.5; word-break: break-word; }
.logs-pager { display: flex; justify-content: flex-end; margin-top: 12px; }
</style>
