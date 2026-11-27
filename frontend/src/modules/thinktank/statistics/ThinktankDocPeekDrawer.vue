<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { errorMessage } from '@/api/errors'
import { getThinktankDocPeek, type DocPeekPayload, type RankedDocItem } from '@/api/thinktankStats'

const props = defineProps<{
  target: RankedDocItem | null
}>()

const visible = defineModel<boolean>({ required: true })
const router = useRouter()

const loading = ref(false)
const detail = ref<DocPeekPayload | null>(null)

watch(
  () => [visible.value, props.target?.id, props.target?.library] as const,
  async ([open, id, lib]) => {
    if (!open || !id || !lib) return
    loading.value = true
    detail.value = null
    try {
      detail.value = await getThinktankDocPeek(lib, id)
    } catch (err) {
      ElMessage.error(errorMessage(err, '加载文档动态失败'))
    } finally {
      loading.value = false
    }
  },
)

function openPreview() {
  const doc = detail.value?.document ?? props.target
  if (!doc) return
  const routeName = {
    knowledge: 'thinktank-knowledge-preview',
    reports: 'thinktank-report-preview',
    proposals: 'thinktank-proposal-preview',
  }[doc.library]
  visible.value = false
  void router.push({ name: routeName, params: { id: doc.id } })
}

const fmt = (n?: number) => (n ?? 0).toLocaleString('zh-CN')
</script>

<template>
  <el-drawer
    v-model="visible"
    :title="target?.title || '文档速览'"
    size="460px"
    destroy-on-close
  >
    <div v-loading="loading">
      <template v-if="detail || target">
        <div class="tt-peek-kpis tabular">
          <div class="tt-peek-kpi">
            <strong>{{ fmt(detail?.document.downloads ?? target?.downloads) }}</strong>
            <span>累计下载</span>
          </div>
          <div class="tt-peek-kpi">
            <strong>{{ fmt(detail?.document.previews ?? target?.previews) }}</strong>
            <span>累计预览</span>
          </div>
          <div class="tt-peek-kpi">
            <strong>{{ fmt(detail?.document.favorites ?? target?.favorites) }}</strong>
            <span>当前收藏</span>
          </div>
        </div>

        <dl class="tt-peek-meta">
          <dt>所属子库</dt>
          <dd>
            <span
              class="tt-lib-chip"
              :class="`tt-lib-chip--${(detail?.document ?? target)!.library}`"
            >
              {{ (detail?.document ?? target)!.library_label }}
            </span>
          </dd>
          <dt>核心分类</dt>
          <dd>{{ (detail?.document ?? target)!.category }}</dd>
          <dt>行业赛道</dt>
          <dd>{{ (detail?.document ?? target)!.industry || '—' }}</dd>
          <dt>归属部门</dt>
          <dd>{{ (detail?.document ?? target)!.dept || '—' }}</dd>
          <dt>上传人</dt>
          <dd>{{ (detail?.document ?? target)!.uploader || '—' }}</dd>
          <dt>上传时间</dt>
          <dd class="tabular">
            {{ (detail?.document ?? target)!.uploaded_at }}
          </dd>
          <dt>文件体积</dt>
          <dd class="tabular">
            {{ (detail?.document ?? target)!.file_size_display }}
            <span v-if="(detail?.document ?? target)!.file_suffix">
              ({{ (detail?.document ?? target)!.file_suffix.replace(/^\./, '').toUpperCase() }})
            </span>
          </dd>
          <dt>标签状态</dt>
          <dd>
            <el-tag
              size="small"
              :type="(detail?.document ?? target)!.is_defined ? 'success' : 'warning'"
              effect="plain"
            >
              {{ (detail?.document ?? target)!.is_defined ? '已定义' : '未定义' }}
            </el-tag>
          </dd>
        </dl>

        <div v-if="detail">
          <h4 class="tt-panel__title">
            近期查阅与操作动态
          </h4>
          <div
            v-if="detail.recent_logs.length > 0"
            class="tt-peek-logs"
            style="margin-top: 10px"
          >
            <div
              v-for="(log, idx) in detail.recent_logs"
              :key="idx"
              class="tt-peek-log-row"
            >
              <span><strong>{{ log.actor_name }}</strong> · {{ log.op_type }}</span>
              <span class="tabular">{{ log.created_at }}</span>
            </div>
          </div>
          <p
            v-else
            class="tt-panel__sub"
          >
            暂无操作流水记录
          </p>
        </div>
      </template>
    </div>

    <template #footer>
      <el-button @click="visible = false">
        关闭
      </el-button>
      <el-button
        type="primary"
        @click="openPreview"
      >
        前往在线预览
      </el-button>
    </template>
  </el-drawer>
</template>

<style scoped src="./thinktank-statistics.css"></style>
