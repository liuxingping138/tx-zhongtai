<script setup lang="ts">
import { computed, ref } from 'vue'

import type { RankedActorItem, RankedDeptItem, RankedDocItem } from '@/api/thinktankStats'
import { avatarToneIndex } from './charts'

const props = defineProps<{
  topDocuments: {
    download: RankedDocItem[]
    preview: RankedDocItem[]
    favorite: RankedDocItem[]
  }
  topContributors: {
    upload: RankedActorItem[]
    active: RankedActorItem[]
    dept: RankedDeptItem[]
  }
  loading: boolean
}>()

defineEmits<{
  'peek-doc': [doc: RankedDocItem]
}>()

const docTab = ref<'download' | 'preview' | 'favorite'>('download')
const userTab = ref<'upload' | 'active' | 'dept'>('upload')

const currentDocs = computed(() => props.topDocuments[docTab.value] ?? [])
const currentActors = computed(() => (userTab.value === 'upload' ? props.topContributors.upload : props.topContributors.active))
const currentDepts = computed(() => props.topContributors.dept)

const maxActorScore = computed(() => {
  const list = currentActors.value
  if (!list.length) return 1
  return Math.max(...list.map(a => (userTab.value === 'upload' ? a.uploads : a.previews)), 1)
})

const maxDeptFiles = computed(() => Math.max(...currentDepts.value.map(d => d.files), 1))

function docPrimaryValue(doc: RankedDocItem): number {
  if (docTab.value === 'download') return doc.downloads
  if (docTab.value === 'preview') return doc.previews
  return doc.favorites
}

const docPrimaryUnit = computed(() => ({ download: '次下载', preview: '次预览', favorite: '人收藏' })[docTab.value])

function docSecondary(doc: RankedDocItem): string {
  if (docTab.value === 'download') return `预览 ${doc.previews} · 收藏 ${doc.favorites}`
  if (docTab.value === 'preview') return `下载 ${doc.downloads} · 收藏 ${doc.favorites}`
  return `预览 ${doc.previews} · 下载 ${doc.downloads}`
}

function extClass(suffix: string): string {
  const clean = suffix.replace(/^\./, '').toLowerCase()
  return clean ? `tt-ext--${clean}` : ''
}

const fmt = (n: number) => n.toLocaleString('zh-CN')
</script>

<template>
  <section class="tt-grid-6-6">
    <div
      class="tt-panel"
      :class="{ 'is-refreshing': loading }"
    >
      <div class="tt-panel__head">
        <div>
          <h2 class="tt-panel__title">
            热门文档 TOP 10
          </h2>
          <p class="tt-panel__sub">
            点击任意文档行可速览详情与近期下载/预览动态
          </p>
        </div>
        <div
          class="tt-seg"
          role="tablist"
          aria-label="文档榜单类型"
        >
          <button
            type="button"
            class="tt-seg__btn"
            :class="{ 'is-active': docTab === 'download' }"
            @click="docTab = 'download'"
          >
            下载榜
          </button>
          <button
            type="button"
            class="tt-seg__btn"
            :class="{ 'is-active': docTab === 'preview' }"
            @click="docTab = 'preview'"
          >
            预览榜
          </button>
          <button
            type="button"
            class="tt-seg__btn"
            :class="{ 'is-active': docTab === 'favorite' }"
            @click="docTab = 'favorite'"
          >
            收藏榜
          </button>
        </div>
      </div>

      <div
        v-if="currentDocs.length > 0"
        class="tt-rank-list"
      >
        <div
          v-for="(doc, idx) in currentDocs"
          :key="`${doc.library}-${doc.id}`"
          class="tt-rank-item"
          role="button"
          tabindex="0"
          @click="$emit('peek-doc', doc)"
          @keydown.enter="$emit('peek-doc', doc)"
        >
          <span
            class="tt-medal tabular"
            :class="idx < 3 ? `tt-medal--${idx + 1}` : ''"
          >{{ idx + 1 }}</span>
          <div class="tt-rank-main">
            <div class="tt-rank-title-row">
              <span
                class="tt-rank-title"
                :title="doc.title"
              >{{ doc.title }}</span>
              <span
                v-if="doc.file_suffix"
                class="tt-ext"
                :class="extClass(doc.file_suffix)"
              >{{ doc.file_suffix.replace(/^\./, '') }}</span>
            </div>
            <div class="tt-rank-sub">
              <span
                class="tt-lib-chip"
                :class="`tt-lib-chip--${doc.library}`"
              >{{ doc.library_label }}</span>
              <span>{{ doc.category }}</span>
              <span v-if="doc.industry && doc.industry !== '无'">{{ doc.industry }}</span>
              <span v-if="doc.uploader">{{ doc.uploader }}</span>
            </div>
          </div>
          <div class="tt-rank-metrics tabular">
            <span class="tt-rank-primary">{{ fmt(docPrimaryValue(doc)) }}<small>{{ docPrimaryUnit }}</small></span>
            <span class="tt-rank-secondary">{{ docSecondary(doc) }}</span>
          </div>
        </div>
      </div>
      <div
        v-else
        class="tt-empty"
      >
        <strong>该周期内暂无热门文档记录</strong>
        <p>当前筛选范围内尚未产生对应的下载、预览或收藏数据。</p>
      </div>
    </div>

    <div
      class="tt-panel"
      :class="{ 'is-refreshing': loading }"
    >
      <div class="tt-panel__head">
        <div>
          <h2 class="tt-panel__title">
            人员与部门贡献 TOP 10
          </h2>
          <p class="tt-panel__sub">
            呈现核心知识沉淀者、高频学习者与部门资产归属
          </p>
        </div>
        <div
          class="tt-seg"
          role="tablist"
          aria-label="贡献榜单类型"
        >
          <button
            type="button"
            class="tt-seg__btn"
            :class="{ 'is-active': userTab === 'upload' }"
            @click="userTab = 'upload'"
          >
            上传贡献榜
          </button>
          <button
            type="button"
            class="tt-seg__btn"
            :class="{ 'is-active': userTab === 'active' }"
            @click="userTab = 'active'"
          >
            高频使用榜
          </button>
          <button
            type="button"
            class="tt-seg__btn"
            :class="{ 'is-active': userTab === 'dept' }"
            @click="userTab = 'dept'"
          >
            部门沉淀榜
          </button>
        </div>
      </div>

      <div
        v-if="userTab === 'dept' && currentDepts.length > 0"
        class="tt-rank-list"
      >
        <div
          v-for="(dept, idx) in currentDepts"
          :key="dept.name"
          class="tt-person-row"
        >
          <span
            class="tt-medal tabular"
            :class="idx < 3 ? `tt-medal--${idx + 1}` : ''"
          >{{ idx + 1 }}</span>
          <span
            class="tt-avatar tt-avatar--dept"
            :class="`tt-avatar--${avatarToneIndex(dept.name)}`"
          >{{ dept.name.slice(0, 1) }}</span>
          <div class="tt-rank-main">
            <div
              class="tt-rank-title"
              :title="dept.name"
            >
              {{ dept.name }}
            </div>
            <div class="tt-rank-sub tabular">
              <span>已定义 {{ fmt(dept.defined) }} 份 · 打标率 {{ dept.defined_rate.toFixed(1) }}%</span>
            </div>
          </div>
          <div class="tt-bar-track">
            <div
              class="tt-bar-fill"
              :style="{ width: `${(dept.files / maxDeptFiles) * 100}%` }"
            />
          </div>
          <div class="tt-rank-metrics tabular">
            <span class="tt-rank-primary">{{ fmt(dept.files) }}<small>份</small></span>
          </div>
        </div>
      </div>

      <div
        v-else-if="userTab !== 'dept' && currentActors.length > 0"
        class="tt-rank-list"
      >
        <div
          v-for="(actor, idx) in currentActors"
          :key="actor.actor_id || actor.name"
          class="tt-person-row"
        >
          <span
            class="tt-medal tabular"
            :class="idx < 3 ? `tt-medal--${idx + 1}` : ''"
          >{{ idx + 1 }}</span>
          <span
            class="tt-avatar"
            :class="`tt-avatar--${avatarToneIndex(actor.actor_id || actor.name)}`"
          >{{ actor.name.slice(0, 1) }}</span>
          <div class="tt-rank-main">
            <div
              class="tt-rank-title"
              :title="actor.name"
            >
              {{ actor.name }}
            </div>
            <div class="tt-rank-sub tabular">
              <span v-if="userTab === 'upload'">治理打标 {{ fmt(actor.governance) }} 次</span>
              <span v-else>下载 {{ fmt(actor.downloads) }} 次 · 活跃 {{ actor.active_days }} 天</span>
            </div>
          </div>
          <div class="tt-bar-track">
            <div
              class="tt-bar-fill"
              :class="userTab === 'active' ? 'tt-bar-fill--reports' : ''"
              :style="{ width: `${((userTab === 'upload' ? actor.uploads : actor.previews) / maxActorScore) * 100}%` }"
            />
          </div>
          <div class="tt-rank-metrics tabular">
            <span class="tt-rank-primary">
              {{ fmt(userTab === 'upload' ? actor.uploads : actor.previews) }}
              <small>{{ userTab === 'upload' ? '份上传' : '次预览' }}</small>
            </span>
          </div>
        </div>
      </div>

      <div
        v-else
        class="tt-empty"
      >
        <strong>暂无贡献排行数据</strong>
        <p>该时间范围或子库下尚未产生对应的上传、查阅或归属部门数据。</p>
      </div>
    </div>
  </section>
</template>

<style scoped src="./thinktank-statistics.css"></style>
