<script setup lang="ts">
import { ArrowLeft, Document, Link, Refresh, Warning } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { errorMessage } from '@/api/errors'
import { getTenderRecord, getTenderContent, type TenderKind, type TenderRecord } from '@/api/tender'
import DetailSections from '@/components/DetailSections.vue'
import { buildDetailSections } from '@/components/detailSections'
import { isolatedHtml } from './content'
import { tenderColumns, tenderDetailGroups } from './fields'

const props = defineProps<{ kind: TenderKind }>()
const route = useRoute()
const router = useRouter()
const record = ref<TenderRecord | null>(null)
const error = ref('')
const loading = ref(false)
const html = ref<string | null>(null)
const contentError = ref('')
const contentLoading = ref(false)
const status = route.query.project_status === '0' ? '0' : '1'
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

const sourceUrl = computed(() => {
  const raw = String(record.value?.from_url ?? '').trim()
  return /^https?:\/\//i.test(raw) ? raw : ''
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
    <header class="detail-topbar">
      <div class="detail-topbar__left">
        <el-button
          :icon="ArrowLeft"
          size="small"
          @click="router.push(back)"
        >
          返回列表
        </el-button>
        <h2>{{ record?.project_name || '项目详情' }}</h2>
      </div>
      <div
        v-if="record"
        class="detail-topbar__meta"
      >
        <el-tag
          size="small"
          :type="status === '1' ? 'success' : 'info'"
          effect="light"
        >
          {{ status === '1' ? '通过' : '未通过' }}
        </el-tag>
        <span
          v-if="record.public_date"
          class="meta-date"
        >发布于 {{ record.public_date }}</span>
        <el-button
          v-if="sourceUrl"
          tag="a"
          :href="sourceUrl"
          target="_blank"
          rel="noopener noreferrer"
          size="small"
          :icon="Link"
        >
          查看原文链接
        </el-button>
      </div>
    </header>

    <div
      v-if="error"
      class="detail-error-card"
      role="alert"
    >
      <span
        class="detail-error-card__icon"
        aria-hidden="true"
      >
        <el-icon :size="20"><Warning /></el-icon>
      </span>
      <div class="detail-error-card__body">
        <strong>获取项目详情失败</strong>
        <p>{{ error }}</p>
      </div>
      <el-button
        size="small"
        type="primary"
        plain
        :icon="Refresh"
        @click="load"
      >
        重试
      </el-button>
    </div>

    <template v-else-if="displayRecord">
      <DetailSections
        :row="displayRecord"
        :sections="sections"
      />

      <section
        v-loading="contentLoading"
        class="tender-body"
      >
        <header class="body-head">
          <div>
            <h3>项目正文</h3>
            <p class="body-note">
              保留公告原始 HTML 排版，已隔离脚本与外部请求
            </p>
          </div>
          <el-button
            v-if="contentError || html !== null"
            size="small"
            :icon="Refresh"
            :loading="contentLoading"
            @click="loadContent"
          >
            {{ contentError ? '重新加载' : '刷新正文' }}
          </el-button>
        </header>

        <div
          v-if="contentError"
          class="content-state"
          role="status"
        >
          <span
            class="content-state__icon"
            aria-hidden="true"
          >
            <el-icon :size="22"><Document /></el-icon>
          </span>
          <div class="content-state__body">
            <strong>暂无可展示的项目正文</strong>
            <p>{{ contentError }}</p>
          </div>
          <div class="content-state__actions">
            <el-button
              size="small"
              type="primary"
              plain
              :icon="Refresh"
              :loading="contentLoading"
              @click="loadContent"
            >
              重试加载
            </el-button>
            <el-button
              v-if="sourceUrl"
              tag="a"
              :href="sourceUrl"
              target="_blank"
              rel="noopener noreferrer"
              size="small"
              :icon="Link"
            >
              打开原发布链接
            </el-button>
          </div>
        </div>

        <div
          v-else-if="html === null"
          class="content-loading"
        >
          正在加载项目正文…
        </div>

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
.tender-detail {
  display: grid;
  gap: var(--zt-space-5);
  padding: var(--zt-space-6);
  background: var(--zt-panel);
  border: 1px solid var(--zt-border);
  border-radius: 12px;
  box-shadow: var(--zt-shadow);
}
.detail-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--zt-space-3);
  padding-bottom: var(--zt-space-4);
  border-bottom: 1px solid var(--zt-divider);
}
.detail-topbar__left {
  display: flex;
  align-items: center;
  gap: var(--zt-space-4);
  min-width: 0;
  flex: 1 1 360px;
}
.detail-topbar__left h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
  color: var(--zt-ink-900);
  overflow-wrap: anywhere;
  line-height: 1.4;
}
.detail-topbar__meta {
  display: flex;
  align-items: center;
  gap: var(--zt-space-3);
  flex-wrap: wrap;
}
.meta-date {
  font-size: 12.5px;
  color: var(--zt-ink-500);
  font-variant-numeric: tabular-nums;
}
.detail-error-card {
  display: flex;
  align-items: center;
  gap: var(--zt-space-4);
  padding: var(--zt-space-4) var(--zt-space-5);
  background: var(--zt-danger-soft);
  border: 1px solid var(--zt-danger-border);
  border-radius: 10px;
}
.detail-error-card__icon {
  display: grid;
  place-items: center;
  flex: 0 0 36px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--zt-panel);
  color: var(--zt-danger);
  border: 1px solid var(--zt-danger-border);
}
.detail-error-card__body {
  flex: 1;
  min-width: 0;
}
.detail-error-card__body strong {
  display: block;
  font-size: 14px;
  color: var(--zt-danger-text);
  margin-bottom: 2px;
}
.detail-error-card__body p {
  margin: 0;
  font-size: 12.5px;
  color: var(--zt-ink-700);
}
.tender-body {
  padding-top: 8px;
  border-top: 1px solid var(--zt-divider);
}
.body-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.body-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  color: var(--zt-ink-900);
}
.body-note {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--zt-ink-500);
}
.content-loading {
  padding: 40px 20px;
  text-align: center;
  font-size: 13px;
  color: var(--zt-ink-500);
  background: var(--zt-surface-subtle);
  border: 1px solid var(--zt-border);
  border-radius: 10px;
}
.content-state {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  padding: 18px 20px;
  background: var(--zt-surface-subtle);
  border: 1px dashed var(--zt-border);
  border-radius: 10px;
}
.content-state__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 10px;
  background: var(--zt-soft);
  color: var(--zt-blue-600);
  flex: none;
}
.content-state__body {
  flex: 1 1 260px;
  min-width: 0;
}
.content-state__body strong {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--zt-ink-900);
}
.content-state__body p {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--zt-ink-500);
  line-height: 1.5;
}
.content-state__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
iframe {
  width: 100%;
  height: 70vh;
  border: 1px solid var(--zt-border);
  border-radius: 10px;
  background: var(--zt-panel);
}
</style>
