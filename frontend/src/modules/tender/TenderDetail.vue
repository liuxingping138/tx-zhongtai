<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { errorMessage } from '@/api/errors'
import { getTenderRecord, getTenderContent, type TenderKind, type TenderRecord } from '@/api/tender'
import { tenderColumns } from './fields'
import { isolatedHtml } from './content'
const props = defineProps<{ kind: TenderKind }>()
const route = useRoute()
const record = ref<TenderRecord | null>(null)
const error = ref('')
const loading = ref(false)
const html = ref<string | null>(null)
const contentError = ref('')
const contentLoading = ref(false)
const status = route.query.project_status === '1' ? '1' : '0'
const columns = tenderColumns(props.kind)
const back = computed(() => ({ name: `tender-${props.kind}`, query: route.query }))
async function load() {
  loading.value = true
  error.value = ''
  try { record.value = await getTenderRecord(props.kind, String(route.params.id), status) }
  catch (cause) { error.value = errorMessage(cause, '详情加载失败') }
  finally { loading.value = false }
}
async function loadContent() {
  contentLoading.value = true
  contentError.value = ''
  try {
    const result = await getTenderContent(props.kind, String(route.params.id), status)
    html.value = isolatedHtml(result.html)
  } catch (cause) { contentError.value = errorMessage(cause, '正文加载失败') }
  finally { contentLoading.value = false }
}
function value(key: string) {
  if (key === 'project_status') return status === '1' ? '人工已处理（信息化）' : '原始数据'
  if (key === 'is_supp_scene') return Number(record.value?.[key]) === 1 ? '已补充' : '未补充'
  return record.value?.[key] ?? '—'
}
onMounted(() => { void load() })
</script>
<template>
  <section
    v-loading="loading"
    class="tender-detail"
  >
    <header>
      <RouterLink :to="back">
        返回列表
      </RouterLink><h2>{{ record?.project_name || '项目详情' }}</h2>
    </header>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
    >
      <el-button @click="load">
        重试
      </el-button>
    </el-alert>
    <template v-else-if="record">
      <el-descriptions
        :column="2"
        border
      >
        <el-descriptions-item
          v-for="column in columns"
          :key="column.prop"
          :label="column.label"
        >
          {{ value(column.prop) }}
        </el-descriptions-item>
      </el-descriptions>
      <section class="tender-body">
        <header>
          <h3>项目正文</h3><el-button
            :loading="contentLoading"
            @click="loadContent"
          >
            {{ html === null ? '加载正文' : '重新加载' }}
          </el-button>
        </header>
        <el-alert
          v-if="contentError"
          :title="contentError"
          type="error"
          :closable="false"
        />
        <p v-else-if="html === null">
          点击加载正文，查看原文排版。
        </p>
        <iframe
          v-else
          :srcdoc="html"
          sandbox=""
          referrerpolicy="no-referrer"
          title="项目原始HTML正文"
        />
      </section>
    </template>
  </section>
</template>
<style scoped>
.tender-detail { padding: 24px; background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: 12px; }
header { display: flex; align-items: center; gap: 20px; margin-bottom: 16px; }
h2 { font-size: 20px; overflow-wrap: anywhere; }
h3 { margin: 0; }
.tender-body { margin-top: 24px; }
.tender-body p { color: var(--zt-ink-500); }
iframe { width: 100%; height: 70vh; border: 1px solid var(--zt-border); background: var(--zt-panel); }
:deep(.el-descriptions__content) { overflow-wrap: anywhere; white-space: pre-wrap; }
</style>
