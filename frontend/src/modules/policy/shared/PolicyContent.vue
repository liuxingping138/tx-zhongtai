<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { errorMessage, isApiError } from '@/api/errors'
import type { PolicyContent } from '@/api/policy'

import { PREVIEW_PARAGRAPHS, paragraphs, shownParagraphs } from './policyContent'

/**
 * 详情抽屉里的「政策正文」：打开时才按源政策 ID 去源库取，不进平台库。
 * 用在基础标签和解读的 `detail-extra` 槽位，父组件按行 ID 加 key，换一条就重新取。
 */
const props = defineProps<{ load: () => Promise<PolicyContent> }>()

const content = ref<PolicyContent | null>(null)
const parts = ref<string[]>([])
const loading = ref(false)
const error = ref('')
// 404 是「这条没有正文」（手工录入、源库已删），不是故障：不给重试。
const missing = ref(false)
const expanded = ref(false)
let ticket = 0

const shown = computed(() => shownParagraphs(parts.value, expanded.value))
const hidden = computed(() => parts.value.length - PREVIEW_PARAGRAPHS)

async function fetchContent(): Promise<void> {
  const current = ++ticket
  loading.value = true
  error.value = ''
  missing.value = false
  try {
    const data = await props.load()
    if (current !== ticket) return
    content.value = data
    parts.value = paragraphs(data.text)
  } catch (caught) {
    if (current !== ticket) return
    content.value = null
    parts.value = []
    missing.value = isApiError(caught) && caught.status === 404
    error.value = errorMessage(caught, '正文加载失败，请重试')
  } finally {
    if (current === ticket) loading.value = false
  }
}

onMounted(fetchContent)
</script>

<template>
  <section
    class="policy-content"
    aria-label="政策正文"
  >
    <header class="policy-content__head">
      <h3>政策正文</h3>
      <span
        v-if="content"
        class="policy-content__meta"
      >{{ content.chars }} 字<template v-if="content.issued_at"> · {{ content.issued_at }}</template></span>
      <a
        v-if="content?.source_url"
        :href="content.source_url"
        target="_blank"
        rel="noopener noreferrer"
        class="policy-content__link"
      >打开原网页</a>
    </header>
    <p
      v-if="loading"
      class="policy-content__muted"
    >
      正文加载中…
    </p>
    <p
      v-else-if="missing"
      class="policy-content__muted"
    >
      {{ error }}
    </p>
    <p
      v-else-if="error"
      class="policy-content__muted"
    >
      {{ error }}
      <el-button
        link
        type="primary"
        @click="fetchContent"
      >
        重试
      </el-button>
    </p>
    <template v-else-if="content">
      <p
        v-for="(part, index) in shown"
        :key="index"
        class="policy-content__paragraph"
      >
        {{ part }}
      </p>
      <el-button
        v-if="hidden > 0"
        link
        type="primary"
        class="policy-content__toggle"
        @click="expanded = !expanded"
      >
        {{ expanded ? '收起' : `展开全文（还有 ${hidden} 段）` }}
      </el-button>
    </template>
  </section>
</template>

<style scoped>
.policy-content { margin-top: 28px; }
.policy-content__head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--zt-border); }
.policy-content__head h3 { margin: 0; font-size: 15px; font-weight: 600; color: var(--zt-ink-900); }
.policy-content__meta { color: var(--zt-ink-500); font-size: 12px; }
.policy-content__link { margin-left: auto; font-size: 13px; color: var(--zt-blue-600); white-space: nowrap; }
.policy-content__muted { margin: 0; color: var(--zt-ink-500); font-size: 14px; line-height: 1.7; }
.policy-content__paragraph { margin: 0 0 10px; font-size: 14px; line-height: 1.8; color: var(--zt-ink-900); overflow-wrap: anywhere; white-space: pre-wrap; }
.policy-content__toggle { padding: 0; }
</style>
