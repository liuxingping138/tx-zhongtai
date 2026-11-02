<script setup lang="ts">
import { computed } from 'vue'

import type { CandidateContext, CandidateDetail, CandidateRow } from '@/api/scenarioCandidates'
import { KIND_NEW, PENDING, levelTitle, pathText, siblingsText } from './candidates'

/** 审核页顶部：这是什么场景、第几级、挂在哪、谁提的、AI 为什么这么写。几行字说完，不重复。 */
const props = defineProps<{
  candidate: CandidateDetail
  context: CandidateContext | null
  /** 来源政策前几条，最近的在前 */
  rows: CandidateRow[]
}>()
const emit = defineEmits<{ openRows: [] }>()

const where = computed(() => {
  const c = props.candidate
  const siblings = siblingsText(props.context?.siblings ?? [])
  if (c.kind !== KIND_NEW) {
    const now = props.context?.industries.length ? `，现在挂在 ${props.context.industries.join('、')}` : ''
    return `场景「${pathText([c.scenario_l1, c.scenario_l2, c.scenario_l3])}」码表里已有${now}；这次要新挂到 ${c.industry}`
  }
  const place = c.parent ? `${c.main_industry} › ${c.parent} 下` : `${c.main_industry} 下新的一级场景`
  const beside = siblings ? `，和 ${siblings} 并列` : props.context ? '，这个位置下码表里还没有别的场景' : ''
  return `${place}${beside}`
})
const otherIndustries = computed(() => props.candidate.industry_count - 1)

const children = computed(() => {
  const list = props.candidate.children
  const more = list.length > 3 ? ` 等 ${list.length} 个` : ''
  return `${list.slice(0, 3).map(child => child.path).join('、')}${more}`
})
const first = computed(() => props.rows[0] ?? null)
const reason = computed(() => props.candidate.reasons[0]?.text ?? '')
</script>

<template>
  <section class="head">
    <div class="head__title">
      <h1>{{ candidate.name }}</h1>
      <span class="head__level">{{ levelTitle(candidate) }}</span>
      <el-tag
        :type="candidate.status === PENDING ? 'info' : 'success'"
        effect="plain"
      >
        {{ candidate.status }}
      </el-tag>
    </div>
    <dl class="head__facts">
      <div>
        <dt>挂在哪</dt>
        <dd>
          {{ where }}<span
            v-if="otherIndustries > 0"
            class="head__muted"
          >（另外还涉及 {{ otherIndustries }} 个行业，见下面「更多」）</span>
        </dd>
      </div>
      <div v-if="candidate.children.length">
        <dt>下级</dt>
        <dd>AI 还写了下级 {{ children }}，跟着它一起处理</dd>
      </div>
      <div>
        <dt>谁提的</dt>
        <dd>
          <el-button
            link
            type="primary"
            :aria-label="`看提出它的全部 ${candidate.policy_count} 条政策`"
            @click="emit('openRows')"
          >
            {{ candidate.policy_count.toLocaleString() }} 条政策
          </el-button>
          <template v-if="first">
            <span>：</span><RouterLink :to="{ name: 'policy-interpretation-review', params: { id: first.id } }">
              {{ first.policy_title }}
            </RouterLink>
            <span class="head__muted"> · {{ first.created_at.slice(0, 10) }} · {{ first.industry }}{{ candidate.policy_count > 1 ? ' 等' : '' }}</span>
          </template>
        </dd>
      </div>
      <div v-if="reason">
        <dt>AI 的理由</dt>
        <dd class="head__reason">
          {{ reason }}
        </dd>
      </div>
    </dl>
  </section>
</template>

<style scoped>
.head {
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-3);
  padding: var(--zt-space-4) var(--zt-space-6);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-panel);
}

.head__title {
  display: flex;
  flex-wrap: wrap;
  gap: var(--zt-space-3);
  align-items: center;
}

.head__title h1 {
  margin: 0;
  font-size: 22px;
}

.head__level {
  padding: 2px 8px;
  border: 1px solid var(--zt-warning-border);
  border-radius: 4px;
  background: var(--zt-warning-soft);
  color: var(--zt-warning-text);
  font-size: 13px;
  font-weight: 500;
}

.head__facts {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  font-size: 14px;
  line-height: 22px;
}

.head__facts div {
  display: flex;
  gap: var(--zt-space-2);
}

.head__facts dt {
  flex-shrink: 0;
  width: 72px;
  color: var(--zt-ink-500);
}

.head__facts dd {
  margin: 0;
  min-width: 0;
}

.head__facts dd .el-button {
  height: auto;
  padding: 0;
  vertical-align: baseline;
}

.head__muted {
  color: var(--zt-ink-500);
}

.head__reason {
  color: var(--zt-ink-700);
}
</style>
