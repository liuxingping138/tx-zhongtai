<script setup lang="ts">
import { computed } from 'vue'

import type { CandidateItem } from '@/api/scenarioCandidates'
import type { CandidateExtras } from './useCandidateExtras'
import { useCandidatePeers } from './useCandidatePeers'
import { KIND_NEW, matchHeadline, matchItems, pathText, siblingsText, similarLabel } from './candidates'

/**
 * 列表行展开后的依据，代替原来的单个场景页面。左边是决定要看的：码表里像它的（每个能「合并到这里」）、
 * 待审里说法相近的；右边三小块：同一位置已有、AI 为什么写它、涉及哪些行业。只放前几项，多的写「等 N 个」。
 */
const props = defineProps<{
  candidate: CandidateItem
  extras: CandidateExtras | undefined
  pending: boolean
  canMerge: boolean
  canAbsorb: boolean
}>()
const emit = defineEmits<{ merge: [path: string[] | null]; rows: []; changed: [ids: string[]] }>()

const SHOWN = 3
const context = computed(() => props.extras?.context ?? null)
const detail = computed(() => props.extras?.detail ?? null)
const loading = computed(() => props.extras?.loading ?? true)
const items = computed(() => matchItems(props.candidate, context.value?.similar ?? []))

const self = computed(() => (props.pending ? props.candidate : null))
const { peers, absorbing, absorb } = useCandidatePeers(self, () => {
  emit('changed', [props.candidate.id])
  return Promise.resolve()
})

const place = computed(() => {
  const c = props.candidate
  if (c.kind !== KIND_NEW) {
    const now = context.value?.industries ?? []
    return now.length ? { title: '这个场景现在挂在', text: now.join('、') } : null
  }
  const text = siblingsText(context.value?.siblings ?? [], SHOWN)
  if (!text) return null
  return { title: c.parent ? `${c.parent} 下已有` : `${c.main_industry} 下已有的一级场景`, text }
})
const children = computed(() => {
  const list = detail.value?.children ?? []
  const more = list.length > SHOWN ? ` 等 ${list.length} 个` : ''
  return list.length ? `${list.slice(0, SHOWN).map(child => child.path).join('、')}${more}` : ''
})
const reasons = computed(() => (detail.value?.reasons ?? []).slice(0, SHOWN))
const industries = computed(() => {
  const list = detail.value?.industries ?? []
  const rest = list.slice(SHOWN)
  return {
    total: list.length,
    top: list.slice(0, SHOWN),
    rest: rest.length ? `其余 ${rest.length} 个行业共 ${rest.reduce((sum, item) => sum + item.rows, 0).toLocaleString()} 行` : '',
  }
})
</script>

<template>
  <div class="expand">
    <section
      class="expand__main"
      :aria-label="`码表里像「${candidate.name}」的场景`"
    >
      <h3>码表里像它的<span v-if="items.length">（{{ items.length }} 个）</span></h3>
      <p
        v-if="extras?.contextError"
        class="expand__muted"
      >
        {{ extras.contextError }}
      </p>
      <ul
        v-if="items.length"
        class="expand__list"
      >
        <li
          v-for="item in items"
          :key="item.text"
          :class="['match', { 'match--ai': item.ai }]"
        >
          <span :class="['match__badge', { 'match__badge--ai': item.ai }]">{{ item.badge }}</span>
          <div class="match__body">
            <p class="match__name">
              {{ item.text }}
            </p>
            <p
              v-if="item.note || item.detail"
              :class="['match__note', { 'match__note--clamp': !item.ai }]"
              :title="item.detail"
            >
              {{ [item.note, item.detail].filter(Boolean).join(' · ') }}
            </p>
          </div>
          <el-button
            v-if="pending && canMerge && item.path"
            size="small"
            :type="item.ai ? 'primary' : 'default'"
            @click="emit('merge', item.path)"
          >
            合并到这里
          </el-button>
        </li>
      </ul>
      <p
        v-else-if="!loading"
        class="expand__muted"
      >
        {{ matchHeadline(candidate, []) }}
      </p>
      <p
        v-if="pending && canMerge"
        class="expand__muted"
      >
        都不是？<el-button
          link
          type="primary"
          @click="emit('merge', null)"
        >
          自己在码表里选一个合并
        </el-button>
      </p>

      <template v-if="peers.length">
        <h3 class="expand__sub">
          待审里还有说法相近的
        </h3>
        <ul class="expand__list">
          <li
            v-for="peer in peers"
            :key="peer.id"
            class="match"
          >
            <span class="match__badge">{{ similarLabel(peer.level) }}</span>
            <div class="match__body">
              <p class="match__name">
                {{ pathText([peer.scenario_l1, peer.scenario_l2, peer.scenario_l3]) }}
              </p>
              <p class="match__note">
                新{{ peer.level_label }} · {{ peer.policy_count.toLocaleString() }} 条政策 · 并进来以后一起决定
              </p>
            </div>
            <el-button
              v-if="canAbsorb"
              size="small"
              :loading="absorbing"
              :disabled="peer.level_label !== candidate.level_label"
              :title="peer.level_label !== candidate.level_label ? '新增级别不同，不能合成一个，请分别决定' : ''"
              @click="absorb(peer)"
            >
              并入本场景
            </el-button>
          </li>
        </ul>
      </template>
    </section>

    <section
      class="expand__side"
      aria-label="依据"
    >
      <p
        v-if="loading"
        class="expand__muted"
      >
        正在取依据…
      </p>
      <p
        v-else-if="extras?.error"
        class="expand__muted"
      >
        {{ extras.error }}
      </p>
      <div v-if="place">
        <h4>{{ place.title }}</h4>
        <p>{{ place.text }}</p>
      </div>
      <div v-if="children">
        <h4>AI 还写了下级</h4>
        <p>{{ children }}，跟着它一起处理</p>
      </div>
      <div v-if="reasons.length">
        <h4>AI 为什么写它</h4>
        <p
          v-for="reason in reasons"
          :key="reason.text"
          class="expand__count"
        >
          <span>{{ reason.count.toLocaleString() }} 条</span>{{ reason.text }}
        </p>
      </div>
      <div v-if="industries.total">
        <h4>涉及哪些行业（{{ industries.total }} 个）</h4>
        <p
          v-for="item in industries.top"
          :key="item.path"
          class="expand__count"
        >
          <span>{{ item.rows.toLocaleString() }} 行</span>{{ item.path }}
        </p>
        <p class="expand__muted">
          <template v-if="industries.rest">
            {{ industries.rest }} ·
          </template><el-button
            link
            type="primary"
            @click="emit('rows')"
          >
            看全部 {{ candidate.policy_count.toLocaleString() }} 条政策
          </el-button>
        </p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.expand {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
  gap: var(--zt-space-8);
  padding: var(--zt-space-4) var(--zt-space-6);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-panel);
  font-size: 13px;
  line-height: 20px;
}

@media (max-width: 1100px) {
  .expand {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--zt-space-4);
  }
}

.expand h3 {
  margin: 0 0 var(--zt-space-2);
  font-size: 14px;
  font-weight: 600;
}

.expand__sub {
  margin-top: var(--zt-space-4) !important;
}

.expand h4 {
  margin: 0 0 2px;
  color: var(--zt-ink-900);
  font-size: 13px;
  font-weight: 600;
}

.expand p {
  margin: 0;
}

.expand__main,
.expand__side {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.expand__side {
  gap: var(--zt-space-3);
  color: var(--zt-ink-700);
}

.expand__muted {
  color: var(--zt-ink-500);
}

.expand__muted .el-button {
  height: auto;
  padding: 0;
  font-size: 13px;
  vertical-align: baseline;
}

/* 条数一列对齐，理由折行时第二行和第一行的字对齐，不顶到最左 */
.expand__count {
  display: flex;
  gap: var(--zt-space-2);
}

.expand__count span {
  flex-shrink: 0;
  min-width: 56px;
  color: var(--zt-ink-500);
}

.expand__list {
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-2);
  margin: 0 0 var(--zt-space-2);
  padding: 0;
  list-style: none;
}

.match {
  display: flex;
  gap: var(--zt-space-3);
  align-items: center;
  padding: var(--zt-space-2) var(--zt-space-3);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
}

.match--ai {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}

.match__badge {
  flex-shrink: 0;
  padding: 0 8px;
  border: 1px solid var(--zt-border);
  border-radius: 4px;
  background: var(--zt-soft);
  color: var(--zt-ink-700);
  font-size: 12px;
  white-space: nowrap;
}

.match__badge--ai {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary);
  color: var(--zt-panel);
}

.match__body {
  flex: 1;
  min-width: 0;
}

.match__name {
  color: var(--zt-ink-900);
  font-size: 14px;
}

.match__note {
  color: var(--zt-ink-500);
  font-size: 12px;
}

.match__note--clamp {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
