<script setup lang="ts">
import { computed } from 'vue'

import type { CandidateContext, CandidateDetail } from '@/api/scenarioCandidates'
import type { Peer } from './useCandidatePeers'
import { PENDING, matchHeadline, matchItems, pathText, similarLabel } from './candidates'

/**
 * 审核页中间：码表里有没有和它是同一个的。AI 认为是同一个的排第一、加框，名称相近的排后面写明是不是同一个行业；
 * 每项一个「合并到这里」。待审里还有说法相近的，列在最后，可以并成一个再决定。
 */
const props = defineProps<{
  candidate: CandidateDetail
  context: CandidateContext | null
  contextError: string
  canMerge: boolean
  peers: Peer[]
  canAbsorb: boolean
  absorbing: boolean
}>()
const emit = defineEmits<{ merge: [path: string[] | null]; absorb: [peer: Peer] }>()

const items = computed(() => matchItems(props.candidate, props.context?.similar ?? []))
const headline = computed(() => matchHeadline(props.candidate, items.value))
const pending = computed(() => props.candidate.status === PENDING)
</script>

<template>
  <section
    class="matches"
    aria-label="码表里像它的场景"
  >
    <div class="matches__head">
      <h2>码表里有没有和它是同一个的</h2>
      <span class="matches__muted">{{ headline }}</span>
    </div>
    <p
      v-if="contextError"
      class="matches__muted"
    >
      {{ contextError }}
    </p>
    <ul
      v-if="items.length"
      class="matches__list"
    >
      <li
        v-for="item in items"
        :key="item.text"
        :class="['match', { 'match--ai': item.ai }]"
      >
        <span :class="['match__badge', { 'match__badge--ai': item.ai }]">{{ item.badge }}</span>
        <div class="match__body">
          <p class="match__name">
            {{ item.text }}<small v-if="item.note">{{ item.note }}</small>
          </p>
          <p
            v-if="item.detail"
            :class="['match__detail', { 'match__detail--clamp': !item.ai }]"
          >
            {{ item.detail }}
          </p>
        </div>
        <el-button
          v-if="pending && canMerge && item.path"
          :type="item.ai ? 'primary' : 'default'"
          @click="emit('merge', item.path)"
        >
          合并到这里
        </el-button>
      </li>
    </ul>
    <p
      v-if="pending && canMerge"
      class="matches__muted"
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
      <h3>待审里还有说法相近的</h3>
      <p class="matches__muted">
        可能是同一个场景换了说法：并进来以后一起决定，以后 AI 再写那个说法也归到这里。
      </p>
      <ul class="matches__list">
        <li
          v-for="peer in peers"
          :key="peer.id"
          class="match"
        >
          <span class="match__badge">{{ similarLabel(peer.level) }}</span>
          <div class="match__body">
            <p class="match__name">
              {{ pathText([peer.scenario_l1, peer.scenario_l2, peer.scenario_l3]) }}<small>新{{ peer.level_label }} · {{ peer.policy_count }} 条政策 · {{ peer.main_industry }}</small>
            </p>
          </div>
          <el-button
            v-if="canAbsorb"
            :loading="absorbing"
            :disabled="peer.level_label !== candidate.level_label"
            :title="peer.level_label !== candidate.level_label ? '新增级别不同，不能合成一个，请分别决定' : ''"
            @click="emit('absorb', peer)"
          >
            并入本场景
          </el-button>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
.matches {
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-3);
  padding: var(--zt-space-4) var(--zt-space-6);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-panel);
}

.matches__head {
  display: flex;
  flex-wrap: wrap;
  gap: var(--zt-space-3);
  align-items: baseline;
}

.matches h2 {
  margin: 0;
  font-size: 16px;
}

.matches h3 {
  margin: var(--zt-space-2) 0 0;
  font-size: 14px;
}

.matches p {
  margin: 0;
}

.matches__muted {
  color: var(--zt-ink-500);
  font-size: 13px;
}

.matches__list {
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.match {
  display: flex;
  gap: var(--zt-space-4);
  align-items: center;
  padding: var(--zt-space-3) var(--zt-space-4);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
}

.match--ai {
  border-color: var(--el-color-primary);
  background: var(--zt-row-hover);
}

.match__badge {
  flex-shrink: 0;
  padding: 2px 8px;
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
  font-weight: 500;
}

.match__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.match__name {
  font-size: 15px;
  font-weight: 600;
}

.match__name small {
  margin-left: var(--zt-space-2);
  color: var(--zt-ink-500);
  font-size: 13px;
  font-weight: 400;
}

.match__detail {
  color: var(--zt-ink-700);
  font-size: 13px;
  line-height: 20px;
}

.match__detail--clamp {
  overflow: hidden;
  color: var(--zt-ink-500);
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
