<script setup lang="ts">
import type { CandidateContext, CandidateDetail, CandidateRow } from '@/api/scenarioCandidates'
import { KIND_NEW, PENDING, pathText } from './candidates'

/** 审核页下半部分：判断依据（码表里的位置、相似的已有场景、AI 理由）在左，来源政策在右。 */
defineProps<{
  candidate: CandidateDetail
  context: CandidateContext | null
  contextError: string
  rows: CandidateRow[]
  canMerge: boolean
}>()
const emit = defineEmits<{ merge: [path: string[]]; openRows: [] }>()
</script>

<template>
  <div class="evidence">
    <section
      class="evidence__panel evidence__panel--main"
      aria-label="判断依据"
    >
      <h2>码表里的位置</h2>
      <p
        v-if="contextError"
        class="evidence__muted"
      >
        {{ contextError }}
      </p>
      <template v-else-if="candidate.kind === KIND_NEW">
        <p class="evidence__muted">
          {{ candidate.parent ? `挂在「${candidate.parent}」下，同级已有：` : `新的一级场景，${candidate.main_industry}下已有的一级场景：` }}
        </p>
        <div class="evidence__chips">
          <span
            v-for="item in context?.siblings ?? []"
            :key="item.name"
            class="evidence__chip"
          >{{ item.name }}<small v-if="item.children">{{ item.children }} 个下级</small></span>
          <span class="evidence__chip evidence__chip--new">＋ {{ candidate.name }}<small>新</small></span>
        </div>
        <p
          v-if="!context?.siblings.length"
          class="evidence__muted"
        >
          码表里这个位置下还没有场景。
        </p>
        <p
          v-if="candidate.children.length"
          class="evidence__muted"
        >
          下级新场景：{{ candidate.children.map(child => `${child.path}（${child.rows} 行）`).join('、') }}
        </p>
      </template>
      <template v-else>
        <p>这个场景码表里已有，现在挂在：{{ context?.industries.join('；') || '—' }}</p>
        <p>这次要新挂到：{{ candidate.industry }}</p>
      </template>

      <h2>相似的已有场景</h2>
      <ul
        v-if="context?.similar.length"
        class="evidence__similar"
      >
        <li
          v-for="item in context.similar"
          :key="pathText(item.path)"
        >
          <el-tag
            :type="item.level === '高' ? 'warning' : 'info'"
            effect="plain"
          >
            {{ item.level }}
          </el-tag>
          <div class="evidence__similar-body">
            <strong>{{ pathText(item.path) }}</strong><span
              v-if="item.industry"
              class="evidence__muted"
            >（{{ item.industry }}）</span>
            <p
              v-if="item.desc"
              class="evidence__muted"
            >
              {{ item.desc }}
            </p>
          </div>
          <el-button
            v-if="candidate.status === PENDING && canMerge"
            size="small"
            @click="emit('merge', item.path)"
          >
            合并到这里
          </el-button>
        </li>
      </ul>
      <p
        v-else
        class="evidence__muted"
      >
        {{ contextError ? '—' : '码表里没有字面相似的场景；意思相近但说法不同的，请对照上面同级的场景判断。' }}
      </p>

      <template v-if="candidate.reasons.length">
        <h2>AI 给的理由</h2>
        <ul class="evidence__reasons">
          <li
            v-for="reason in candidate.reasons"
            :key="reason.text"
          >
            <span class="evidence__count">{{ reason.count }} 条</span>{{ reason.text }}
          </li>
        </ul>
      </template>
    </section>

    <section
      class="evidence__panel"
      aria-label="来源政策"
    >
      <div class="evidence__head">
        <h2>来源政策</h2>
        <el-button
          link
          type="primary"
          @click="emit('openRows')"
        >
          查看全部 {{ candidate.policy_count.toLocaleString() }} 条 →
        </el-button>
      </div>
      <ul class="evidence__rows">
        <li
          v-for="row in rows"
          :key="row.id"
        >
          <RouterLink :to="{ name: 'policy-interpretation-review', params: { id: row.id } }">
            {{ row.policy_title }}
          </RouterLink>
          <span class="evidence__muted">{{ row.created_at.slice(0, 10) }} · {{ row.industry }} · {{ row.opportunity_type }}</span>
          <span
            v-if="row.remark"
            class="evidence__muted"
          >AI：{{ row.remark }}</span>
        </li>
      </ul>
      <p class="evidence__muted">
        涉及行业：{{ candidate.industries.map(item => `${item.path}（${item.rows} 行）`).join('；') }}
      </p>
    </section>
  </div>
</template>

<style scoped>
.evidence {
  display: flex;
  flex-wrap: wrap;
  gap: var(--zt-space-4);
  align-items: flex-start;
}

.evidence__panel {
  flex: 1 1 380px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-2);
  padding: var(--zt-space-4) var(--zt-space-6);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-panel);
}

.evidence__panel--main {
  flex: 1.3 1 520px;
}

.evidence h2 {
  margin: var(--zt-space-2) 0 0;
  font-size: 15px;
}

.evidence p {
  margin: 0;
  line-height: 22px;
}

.evidence__muted {
  color: var(--zt-ink-500);
  font-size: 13px;
  line-height: 20px;
}

.evidence__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--zt-space-2);
}

.evidence__chip {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 4px 10px;
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-surface-subtle);
  font-size: 13px;
}

.evidence__chip small {
  color: var(--zt-ink-500);
}

.evidence__chip--new {
  border: 1px dashed var(--zt-warning);
  background: var(--zt-warning-soft);
  color: var(--zt-warning-text);
  font-weight: 600;
}

.evidence__chip--new small {
  color: var(--zt-warning-text);
}

.evidence__similar,
.evidence__reasons,
.evidence__rows {
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.evidence__similar li {
  display: flex;
  gap: var(--zt-space-3);
  align-items: flex-start;
  padding: var(--zt-space-3);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
}

.evidence__similar-body {
  flex: 1;
  min-width: 0;
}

.evidence__reasons li {
  display: flex;
  gap: var(--zt-space-3);
  font-size: 13px;
  line-height: 20px;
}

.evidence__count {
  flex-shrink: 0;
  min-width: 40px;
  color: var(--zt-ink-500);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.evidence__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.evidence__rows li {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-bottom: var(--zt-space-2);
  border-bottom: 1px solid var(--zt-divider);
}
</style>
