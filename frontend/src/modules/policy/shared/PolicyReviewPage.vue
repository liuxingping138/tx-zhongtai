<script setup lang="ts" generic="T extends { id: string }">
import { computed, ref, type ComponentPublicInstance } from 'vue'
import { ArrowLeft, ArrowRight, EditPen } from '@element-plus/icons-vue'

import type { PolicyContent as PolicyContentData } from '@/api/policy'
import { fieldText, fieldValue } from '@/components/cellValue'
import type { DataColumn } from '@/components/dataColumns'
import DetailFieldTable from '@/components/DetailFieldTable.vue'
import DetailSections from '@/components/DetailSections.vue'
import { buildDetailSections } from '@/components/detailSections'
import type { EditorGroup } from '@/components/editorGroups'
import GroupedFields from '@/components/GroupedFields.vue'
import type { EditorFieldsHandle } from '@/composables/useRecordEditor'
import PolicyContent from './PolicyContent.vue'
import type { useReviewRecord } from './useReviewRecord'

/**
 * 政策核对页：上面是概要，左边按分组的字段表，右边是政策正文，可收起。
 * 先看结论再翻原文，所以字段在左、正文在右。点「编辑」各组一起变成输入框，底部一次保存，改的时候正文还在右边对照。
 */
const props = defineProps<{
  review: ReturnType<typeof useReviewRecord<T>>
  columns: readonly DataColumn[]
  groups: readonly EditorGroup[]
  titleKey: string
  /** 概要里一眼要看到的字段。 */
  facts: readonly string[]
  listLabel: string
  canWrite: boolean
  status?: { text: string; type: 'success' | 'warning' | 'danger' | 'info' }
  loadContent: (id: string) => Promise<PolicyContentData>
  /** 要提醒的分组：页签旁一个小圆点，值是说明（悬停可见，读屏也读得到） */
  tabMarks?: Record<string, string>
}>()

// 拆成顶层 ref，模板里才会自动解包。
const {
  record, ready, loading, loadError, load, total, position, hasPrev, hasNext, moving, move, backToList,
  editing, draft, saving, saveError, fields, dirty, startEdit, cancelEdit, saveEdit,
} = props.review

const sections = computed(() => buildDetailSections(props.columns, props.groups))
const groupOf = (title: string) => props.groups.filter(group => group.title === title)

// 编辑时每组一份输入框，保存前逐组校验。倒着校验：每组校验失败都会把焦点移到自己的错误上，最后停在最靠前的那组。
const handles = new Map<string, EditorFieldsHandle>()
function bindFields(title: string) {
  return (instance: Element | ComponentPublicInstance | null) => {
    if (instance) handles.set(title, instance as unknown as EditorFieldsHandle)
    else handles.delete(title)
  }
}
fields.value = {
  async validate() {
    let ok = true
    for (const group of [...props.groups].reverse()) {
      const handle = handles.get(group.title)
      if (handle && !await handle.validate()) ok = false
    }
    return ok
  },
  async setError(key, message) {
    const group = props.groups.find(item => item.fields.some(field => field.key === key))
    if (group) await handles.get(group.title)?.setError(key, message)
  },
}

const facts = computed(() => {
  const row = record.value
  if (!row) return []
  const byProp = new Map(props.columns.map(col => [col.prop, col]))
  const items = props.facts.flatMap((key) => {
    const col = byProp.get(key)
    return col ? [{ label: col.label, text: fieldText(row, col) }] : []
  })
  const stamp = (timeKey: string, nameKey: string, label: string) => {
    const col = byProp.get(timeKey)
    if (!col || !fieldValue(row, timeKey)) return
    const who = fieldValue(row, nameKey)
    items.push({ label, text: who ? `${fieldText(row, col)} · ${who}` : fieldText(row, col) })
  }
  stamp('created_at', 'created_by_name', '入库')
  stamp('updated_at', 'updated_by_name', '最近更新')
  return items
})

// 分组导航：点组名滚到那一组，滚动时高亮当前看到的组。
const scroller = ref<HTMLElement>()
const active = ref('')
function sectionElements() {
  return [...(scroller.value?.querySelectorAll<HTMLElement>('[data-section]') ?? [])]
}
function scrollToSection(title: string) {
  const target = sectionElements().find(el => el.dataset.section === title)
  if (!scroller.value || !target) return
  const smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches
  scroller.value.scrollTo({ top: target.offsetTop - 8, behavior: smooth ? 'smooth' : 'auto' })
  active.value = title
}
function syncActive() {
  const top = (scroller.value?.scrollTop ?? 0) + 24
  const passed = sectionElements().filter(el => el.offsetTop <= top)
  active.value = passed.at(-1)?.dataset.section ?? sections.value[0]?.title ?? ''
}

// 正文默认打开；收起后字段表占满整行。只是本浏览器的习惯，存不了也不影响使用。
const CONTENT_KEY = 'zt:policy-review:content'
function readContentOpen() {
  try {
    return localStorage.getItem(CONTENT_KEY) !== 'closed'
  } catch {
    return true
  }
}
const contentOpen = ref(readContentOpen())
function setContentOpen(open: boolean) {
  contentOpen.value = open
  try {
    localStorage.setItem(CONTENT_KEY, open ? 'open' : 'closed')
  } catch {
    // 浏览器禁用了本地存储时只在本页记住。
  }
}
</script>

<template>
  <div class="review">
    <div class="review__bar">
      <el-button
        link
        type="primary"
        :icon="ArrowLeft"
        @click="backToList"
      >
        返回{{ listLabel }}
      </el-button>
      <template v-if="position !== null">
        <span class="review__position">第 {{ position + 1 }} 条<template v-if="total !== null">，共 {{ total }} 条（当前筛选）</template></span>
        <el-button
          :icon="ArrowLeft"
          :disabled="!hasPrev || moving"
          @click="move(-1)"
        >
          上一条
        </el-button>
        <el-button
          :disabled="!hasNext || moving"
          @click="move(1)"
        >
          下一条<el-icon class="el-icon--right">
            <ArrowRight />
          </el-icon>
        </el-button>
      </template>
    </div>

    <div
      v-if="loading && !record"
      v-loading="true"
      class="review__placeholder"
    />
    <el-alert
      v-else-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
    >
      <el-button
        link
        type="primary"
        @click="load"
      >
        重试
      </el-button>
    </el-alert>
    <template v-else-if="record">
      <section
        class="review__summary"
        aria-label="概要"
      >
        <div class="review__title-row">
          <h1>{{ fieldValue(record, titleKey) || '未命名记录' }}</h1>
          <el-tag
            v-if="status"
            :type="status.type"
            disable-transitions
          >
            {{ status.text }}
          </el-tag>
          <div class="review__actions">
            <slot
              name="actions"
              :row="record"
              :editing="editing"
              :ready="ready"
            />
          </div>
        </div>
        <dl class="review__facts">
          <div
            v-for="fact in facts"
            :key="fact.label"
          >
            <dt>{{ fact.label }}</dt>
            <dd>{{ fact.text }}</dd>
          </div>
        </dl>
        <slot
          name="summary-extra"
          :row="record"
        />
      </section>

      <div
        class="review__body"
        :class="{ 'is-content-closed': !contentOpen }"
      >
        <section
          class="review__panel"
          aria-label="记录详情"
        >
          <nav
            class="review__tabs"
            aria-label="详情分组"
          >
            <button
              v-for="section in sections"
              :key="section.title"
              type="button"
              :class="{ 'is-active': (active || sections[0]?.title) === section.title }"
              @click="scrollToSection(section.title)"
            >
              {{ section.title }}<span
                v-if="tabMarks?.[section.title]"
                class="review__mark"
                :title="tabMarks[section.title]"
              ><span class="sr-only">（{{ tabMarks[section.title] }}）</span></span>
            </button>
            <el-button
              v-if="canWrite && !editing"
              class="review__edit"
              :icon="EditPen"
              :disabled="!ready"
              @click="startEdit"
            >
              编辑
            </el-button>
          </nav>
          <div
            ref="scroller"
            class="review__scroll"
            @scroll.passive="syncActive"
          >
            <el-form
              novalidate
              label-position="top"
              :disabled="saving"
              @submit.prevent="saveEdit"
            >
              <DetailSections
                :row="record"
                :sections="sections"
              >
                <template #body="{ section }">
                  <slot
                    name="section-extra"
                    :section="section.title"
                    :row="record"
                  />
                  <div
                    v-if="editing && groupOf(section.title).length"
                    class="review__editor"
                  >
                    <GroupedFields
                      :ref="bindFields(section.title)"
                      :model-value="draft"
                      :groups="groupOf(section.title)"
                      bare
                    />
                  </div>
                  <DetailFieldTable
                    v-else
                    :row="record"
                    :fields="section.fields"
                  />
                </template>
              </DetailSections>
            </el-form>
          </div>
          <div
            v-if="editing"
            class="review__edit-bar"
          >
            <p
              v-if="saveError"
              class="review__save-error"
              role="alert"
            >
              {{ saveError }}
            </p>
            <span
              v-else-if="dirty"
              class="review__dirty"
              role="status"
            >有未保存的修改</span>
            <el-button
              :disabled="saving"
              @click="cancelEdit"
            >
              取消
            </el-button>
            <el-button
              type="primary"
              :loading="saving"
              @click="saveEdit"
            >
              保存
            </el-button>
          </div>
        </section>

        <section
          v-if="contentOpen"
          class="review__panel review__content"
        >
          <PolicyContent
            :key="record.id"
            panel
            :load="() => loadContent(record!.id)"
          >
            <template #actions>
              <el-button
                link
                @click="setContentOpen(false)"
              >
                收起<el-icon class="el-icon--right">
                  <ArrowRight />
                </el-icon>
              </el-button>
            </template>
          </PolicyContent>
        </section>
        <button
          v-else
          type="button"
          class="review__content-rail"
          aria-label="展开政策正文"
          @click="setContentOpen(true)"
        >
          <el-icon><ArrowLeft /></el-icon>
          <span>政策正文</span>
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.review { display: flex; flex-direction: column; gap: 12px; height: calc(100dvh - var(--workspace-header-height) - 48px); min-height: 560px; }
.review__bar { flex: none; display: flex; align-items: center; gap: 8px; }
.review__bar :deep(.el-button + .el-button) { margin-left: 0; }
.review__position { margin-left: auto; color: var(--zt-ink-500); font-size: 13px; font-variant-numeric: tabular-nums; }
.review__placeholder { flex: 1; min-height: 240px; }

.review__summary { flex: none; display: flex; flex-direction: column; gap: 10px; padding: 14px 20px; background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: var(--zt-radius); }
.review__title-row { display: flex; align-items: center; gap: 12px; min-width: 0; }
.review__title-row h1 { min-width: 0; margin: 0; color: var(--zt-ink-900); font-size: 20px; font-weight: 600; line-height: 1.5; overflow-wrap: anywhere; }
.review__actions { flex: none; display: flex; gap: 8px; margin-left: auto; }
.review__actions :deep(.el-button + .el-button) { margin-left: 0; }
.review__facts { display: flex; flex-wrap: wrap; gap: 4px 32px; margin: 0; font-size: 13px; }
.review__facts div { display: flex; gap: 8px; }
.review__facts dt { color: var(--zt-ink-500); }
.review__facts dd { margin: 0; color: var(--zt-ink-900); }

.review__body { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 16px; }
.review__body.is-content-closed { grid-template-columns: minmax(0, 1fr) 40px; }
.review__panel { min-height: 0; display: flex; flex-direction: column; background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: var(--zt-radius); }
.review__tabs { flex: none; display: flex; gap: 28px; padding: 0 20px; border-bottom: 1px solid var(--zt-border); }
.review__tabs button { height: 44px; padding: 0; border: 0; background: none; color: var(--zt-ink-700); font: inherit; font-size: 14px; cursor: pointer; }
.review__tabs button.is-active { color: var(--zt-blue-600); font-weight: 600; box-shadow: inset 0 -2px 0 var(--zt-blue-600); }
.review__mark { display: inline-block; width: 6px; height: 6px; margin-left: 5px; border-radius: 50%; background: var(--zt-warning); vertical-align: 2px; }
.review__scroll { position: relative; flex: 1; min-height: 0; overflow-y: auto; padding: 16px 20px 24px; }
.review__edit { align-self: center; margin-left: auto; }
.review__edit-bar { flex: none; display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 8px; padding: 12px 20px; border-top: 1px solid var(--zt-border); }
.review__edit-bar :deep(.el-button + .el-button) { margin-left: 0; }
.review__dirty { margin-right: auto; color: var(--zt-warning-text); font-size: 12px; }
.review__save-error { flex: 1 1 280px; margin: 0 auto 0 0; color: var(--zt-danger-text); font-size: 13px; line-height: 1.5; }
.review__editor { padding: 14px 16px; border-radius: var(--zt-radius); background: var(--el-color-primary-light-9); box-shadow: inset 0 0 0 1px var(--el-color-primary-light-7); }
.review__content { overflow-y: auto; padding: 0 20px 20px; }
.review__content :deep(.policy-content__head) { padding-top: 14px; }
.review__content-rail { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 14px 0; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); color: var(--zt-ink-700); font: inherit; font-size: 13px; cursor: pointer; }
.review__content-rail span { writing-mode: vertical-rl; letter-spacing: 2px; }
.review__content-rail:hover { color: var(--zt-blue-600); }
</style>
