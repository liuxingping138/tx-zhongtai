<script setup lang="ts">
import { computed } from 'vue'

import type { CandidateContext, CandidateDetail } from '@/api/scenarioCandidates'
import AuditLogButton from '@/components/AuditLogButton.vue'
import { RESOURCE } from './candidates'

/** 审核页最下面收起的「更多」：做决定时用不太上、偶尔要查的。 */
const props = defineProps<{ candidate: CandidateDetail; context: CandidateContext | null }>()

const siblings = computed(() =>
  [...(props.context?.siblings ?? [])]
    .sort((a, b) => b.children - a.children)
    .map(item => (item.children ? `${item.name}（${item.children} 个下级）` : item.name))
    .join('、'),
)
</script>

<template>
  <details class="more">
    <summary>
      更多：解读 {{ candidate.row_count.toLocaleString() }} 行 · 首次出现 {{ candidate.first_seen_at.slice(0, 10) }} · 最近出现 {{ candidate.last_seen_at.slice(0, 10) }} · 涉及行业、同级场景、操作记录
    </summary>
    <dl class="more__facts">
      <div>
        <dt>涉及行业</dt>
        <dd>{{ candidate.industries.map(item => `${item.path}（${item.rows} 行）`).join('；') || '—' }}</dd>
      </div>
      <div v-if="siblings">
        <dt>同一位置已有</dt>
        <dd>{{ siblings }}</dd>
      </div>
      <div v-if="candidate.reasons.length > 1">
        <dt>AI 写过的理由</dt>
        <dd>
          <p
            v-for="reason in candidate.reasons"
            :key="reason.text"
          >
            {{ reason.count }} 条：{{ reason.text }}
          </p>
        </dd>
      </div>
      <div>
        <dt>操作记录</dt>
        <dd><AuditLogButton :module="RESOURCE" /></dd>
      </div>
    </dl>
  </details>
</template>

<style scoped>
.more {
  color: var(--zt-ink-500);
  font-size: 13px;
}

.more summary {
  color: var(--zt-ink-700);
  cursor: pointer;
}

.more__facts {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: var(--zt-space-2) 0 0;
  padding-left: var(--zt-space-4);
}

.more__facts div {
  display: flex;
  gap: var(--zt-space-2);
  align-items: baseline;
}

.more__facts dt {
  flex-shrink: 0;
  width: 96px;
}

.more__facts dd {
  margin: 0;
  min-width: 0;
  color: var(--zt-ink-700);
}

.more__facts p {
  margin: 0;
}
</style>
