<script setup lang="ts">
import { ArrowLeft, Document, Link, Refresh, Warning } from '@element-plus/icons-vue'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { errorMessage } from '@/api/errors'
import { getTenderRecord, getTenderContent, type TenderKind, type TenderRecord } from '@/api/tender'
import DetailSections from '@/components/DetailSections.vue'
import DetailSkeleton from '@/components/DetailSkeleton.vue'
import ParagraphSkeleton from '@/components/ParagraphSkeleton.vue'
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
const status = computed<'0' | '1'>(() => (route.query.project_status === '0' ? '0' : '1'))
const sections = computed(() => buildDetailSections(tenderColumns(props.kind), tenderDetailGroups(props.kind)))
const back = computed(() => ({ name: `tender-${props.kind}`, query: route.query }))

const displayRecord = computed(() => {
  if (!record.value) return null
  return {
    ...record.value,
    project_status: status.value === '1' ? '通过' : '未通过',
    is_supp_scene: Number(record.value.is_supp_scene) === 1 ? '已补充' : '未补充',
  }
})

const sourceUrl = computed(() => {
  const raw = String(record.value?.from_url ?? '').trim()
  return /^https?:\/\//i.test(raw) ? raw : ''
})

let loadSeq = 0
let contentSeq = 0

async function load() {
  const seq = ++loadSeq
  loading.value = true
  error.value = ''
  try {
    const next = await getTenderRecord(props.kind, String(route.params.id), status.value)
    if (seq === loadSeq) record.value = next
  } catch (cause) {
    if (seq === loadSeq) error.value = errorMessage(cause, '详情加载失败')
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

async function loadContent() {
  const seq = ++contentSeq
  contentLoading.value = true
  contentError.value = ''
  try {
    const result = await getTenderContent(props.kind, String(route.params.id), status.value)
    if (seq === contentSeq) html.value = isolatedHtml(result.html)
  } catch (cause) {
    if (seq === contentSeq) contentError.value = errorMessage(cause, '正文加载失败')
  } finally {
    if (seq === contentSeq) contentLoading.value = false
  }
}

watch(
  () => [props.kind, String(route.params.id), status.value] as const,
  () => {
    void load()
    void loadContent()
  },
  { immediate: true },
)
</script>

<template>
  <section class="tender-detail">
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

    <DetailSkeleton
      v-if="loading && !record"
      :sections="2"
      :fields-per-section="6"
      :show-article="true"
    />

    <div
      v-else-if="error"
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

      <section class="tender-body">
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

        <ParagraphSkeleton
          v-else-if="html === null"
          :lines="8"
        />

        <div
          v-else-if="!html.trim()"
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
            <strong>暂无公告原始正文内容</strong>
            <p>该条目未提取到 HTML 正文，您可以前往官方发布页面查看原始信息。</p>
          </div>
          <div class="content-state__actions">
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

<style scoped src="./tender-detail.css"></style>
