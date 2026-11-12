<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { errorMessage } from '@/api/errors'
import { getTenderRecord, getTenderContent, type TenderKind, type TenderRecord } from '@/api/tender'
import DetailSections from '@/components/DetailSections.vue'
import { buildDetailSections } from '@/components/detailSections'
import { isolatedHtml } from './content'
import { tenderColumns, tenderDetailGroups } from './fields'

const props = defineProps<{ kind: TenderKind }>()
const route = useRoute()
const record = ref<TenderRecord | null>(null)
const error = ref('')
const loading = ref(false)
const html = ref<string | null>(null)
const contentError = ref('')
const contentLoading = ref(false)
const status = route.query.project_status === '1' ? '1' : '0'
const sections = computed(() => buildDetailSections(tenderColumns(props.kind), tenderDetailGroups(props.kind)))
const back = computed(() => ({ name: `tender-${props.kind}`, query: route.query }))

const displayRecord = computed(() => {
  if (!record.value) return null
  return {
    ...record.value,
    project_status: status === '1' ? '通过' : '未通过',
    is_supp_scene: Number(record.value.is_supp_scene) === 1 ? '已补充' : '未补充',
  }
})

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

onMounted(() => {
  void load()
  void loadContent()
})
</script>

<template>
  <section
    v-loading="loading"
    class="tender-detail"
  >
    <header class="detail-head">
      <RouterLink :to="back">
        返回列表
      </RouterLink>
      <h2>{{ record?.project_name || '项目详情' }}</h2>
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
    <template v-else-if="displayRecord">
      <DetailSections
        :row="displayRecord"
        :sections="sections"
      />
      <section
        v-loading="contentLoading"
        class="tender-body"
      >
        <header class="detail-head">
          <h3>项目正文</h3>
          <el-button
            v-if="contentError || html !== null"
            size="small"
            :loading="contentLoading"
            @click="loadContent"
          >
            {{ contentError ? '重试' : '重新加载' }}
          </el-button>
        </header>
        <el-alert
          v-if="contentError"
          :title="contentError"
          type="error"
          :closable="false"
        />
        <p v-else-if="html === null">
          正在加载正文…
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
.detail-head { display: flex; align-items: center; gap: 20px; margin-bottom: 16px; }
h2 { margin: 0; font-size: 20px; overflow-wrap: anywhere; }
h3 { margin: 0; font-size: 16px; }
.tender-body { margin-top: 24px; }
.tender-body p { color: var(--zt-ink-500); }
iframe { width: 100%; height: 70vh; border: 1px solid var(--zt-border); border-radius: 8px; background: var(--zt-panel); }
</style>
