<script setup lang="ts">
import type { PromptTemplate } from '@/api/ai'
import { smartModelParts } from '../shared/aiText'
import { shortTime } from './sampleView'
import { releaseState, sampleState } from './templateStatus'

export type ListSortKey = 'updated_at' | 'title' | 'release' | 'fields'

defineProps<{
  rows: PromptTemplate[]
  showTasks: boolean
  loading: boolean
  sortKey: ListSortKey
  sortAsc: boolean
  tasksOf: (item: PromptTemplate) => string[]
}>()

const emit = defineEmits<{
  open: [template: PromptTemplate]
  sort: [key: ListSortKey]
}>()

function sortArrow(activeKey: ListSortKey, asc: boolean, col: ListSortKey): string {
  if (activeKey !== col) return '↕'
  return asc ? '↑' : '↓'
}

function outputPreview(fields: string[]): string {
  if (!fields.length) return ''
  return fields.length <= 2 ? fields.join('、') : `${fields.slice(0, 2).join('、')}…`
}

function sampleHover(row: PromptTemplate): string {
  const state = sampleState(row)
  return state.detail ? `${state.text} · ${state.detail}` : state.text
}

function releaseHover(row: PromptTemplate): string {
  const state = releaseState(row)
  return state.detail ? `${state.text}（线上：${state.detail}）` : state.text
}
</script>

<template>
  <div
    class="prompt-list__table-wrap"
    :class="{ 'is-refreshing': loading }"
  >
    <table class="prompt-table">
      <colgroup>
        <col class="col-title">
        <col class="col-cat">
        <col
          v-if="showTasks"
          class="col-tasks"
        >
        <col class="col-release">
        <col class="col-sample">
        <col class="col-fields">
        <col class="col-model">
        <col class="col-creator">
        <col class="col-updated">
        <col class="col-open">
      </colgroup>
      <thead>
        <tr>
          <th scope="col">
            <button
              type="button"
              class="prompt-sort-btn"
              :class="{ 'is-sorted': sortKey === 'title' }"
              @click="emit('sort', 'title')"
            >
              <span>模板名称</span>
              <span
                class="prompt-sort-arrow"
                aria-hidden="true"
              >{{ sortArrow(sortKey, sortAsc, 'title') }}</span>
            </button>
          </th>
          <th scope="col">
            类型
          </th>
          <th
            v-if="showTasks"
            scope="col"
          >
            定时任务
          </th>
          <th scope="col">
            <button
              type="button"
              class="prompt-sort-btn"
              :class="{ 'is-sorted': sortKey === 'release' }"
              @click="emit('sort', 'release')"
            >
              <span>上线状态</span>
              <span
                class="prompt-sort-arrow"
                aria-hidden="true"
              >{{ sortArrow(sortKey, sortAsc, 'release') }}</span>
            </button>
          </th>
          <th scope="col">
            样本试跑
          </th>
          <th scope="col">
            <button
              type="button"
              class="prompt-sort-btn"
              :class="{ 'is-sorted': sortKey === 'fields' }"
              @click="emit('sort', 'fields')"
            >
              <span>输出字段</span>
              <span
                class="prompt-sort-arrow"
                aria-hidden="true"
              >{{ sortArrow(sortKey, sortAsc, 'fields') }}</span>
            </button>
          </th>
          <th scope="col">
            模型
          </th>
          <th scope="col">
            创建人
          </th>
          <th scope="col">
            <button
              type="button"
              class="prompt-sort-btn"
              :class="{ 'is-sorted': sortKey === 'updated_at' }"
              @click="emit('sort', 'updated_at')"
            >
              <span>最近更新</span>
              <span
                class="prompt-sort-arrow"
                aria-hidden="true"
              >{{ sortArrow(sortKey, sortAsc, 'updated_at') }}</span>
            </button>
          </th>
          <th
            scope="col"
            class="is-right"
            aria-label="操作"
          />
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.id"
          @click="emit('open', row)"
        >
          <td>
            <div class="prompt-cell-main">
              <router-link
                class="prompt-list__name"
                :to="{ name: 'ai-prompt-edit', params: { id: row.id } }"
                :title="row.title"
                @click.stop
              >
                {{ row.title }}
              </router-link>
              <span
                v-if="!row.editable"
                class="prompt-list__readonly"
              >只读</span>
            </div>
          </td>

          <td>
            <span class="prompt-list__cat">{{ row.category_name }}</span>
          </td>

          <td v-if="showTasks">
            <div
              v-if="tasksOf(row).length"
              class="prompt-list__task-cell"
              :title="`正在用于定时任务：${tasksOf(row).join('、')}`"
            >
              <span class="prompt-list__task-pill">{{ tasksOf(row)[0] }}</span>
              <span
                v-if="tasksOf(row).length > 1"
                class="prompt-list__task-more"
              >+{{ tasksOf(row).length - 1 }}</span>
            </div>
            <span
              v-else
              class="prompt-list__none"
            >—</span>
          </td>

          <td>
            <div
              class="prompt-cell-release"
              :title="releaseHover(row)"
            >
              <span
                class="prompt-list__state"
                :class="`is-${releaseState(row).kind}`"
              ><span class="prompt-list__state-text">{{ releaseState(row).compact }}</span></span>
              <router-link
                v-if="row.release?.unreleased_changes.length"
                class="prompt-list__diff"
                :to="{ name: 'ai-prompt-edit', params: { id: row.id }, query: { review: '1' } }"
                :title="`草稿改了${row.release.unreleased_changes.join('、')}，尚未上线`"
                @click.stop
              >
                看改动
              </router-link>
            </div>
          </td>

          <td>
            <span
              class="prompt-list__sample"
              :class="`is-${sampleState(row).kind}`"
              :title="sampleHover(row)"
            >{{ sampleState(row).compact }}</span>
          </td>

          <td>
            <span
              v-if="row.fields.length"
              class="prompt-list__fields"
              :title="row.fields.join('、')"
            >
              <strong>{{ row.fields.length }} 个</strong>
              <span>{{ outputPreview(row.fields) }}</span>
            </span>
            <span
              v-else
              class="prompt-list__none"
            >自由文本</span>
          </td>

          <td>
            <div
              class="prompt-model-cell"
              :title="row.model_name || '未选模型'"
            >
              <span class="prompt-model-cell__family">{{ smartModelParts(row.model_name).family }}</span>
              <span
                v-if="smartModelParts(row.model_name).tier"
                class="prompt-model-cell__tier"
              >· {{ smartModelParts(row.model_name).tier }}</span>
              <span
                v-if="smartModelParts(row.model_name).online"
                class="prompt-model-cell__net"
              >联网</span>
            </div>
          </td>

          <td>
            <span
              class="prompt-list__creator"
              :title="row.created_by_name || '—'"
            >{{ row.created_by_name || '—' }}</span>
          </td>

          <td>
            <span
              class="prompt-list__time"
              :title="`${row.updated_by_name} · ${row.updated_at}`"
            >{{ shortTime(row.updated_at) }}</span>
          </td>

          <td class="is-right">
            <span class="prompt-list__open">打开 →</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
