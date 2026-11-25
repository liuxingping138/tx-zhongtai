<script setup lang="ts">
import type { ModelConfig } from '@/api/ai'
import {
  listExtraPrices,
  mainPriceDisplay,
  PROVIDER_LABELS,
  serviceTierBadge,
  shortEndpoint,
  thinkingBadgeText,
  type ExtraPriceChip,
  type ModelSortKey,
  type PriceUnit,
} from './modelView'

const props = defineProps<{
  rows: ModelConfig[]
  unit: PriceUnit
  canWrite: boolean
  toggling: string
  hasFilters: boolean
  sortKey: ModelSortKey
  sortAsc: boolean
}>()

const emit = defineEmits<{
  view: [row: ModelConfig]
  edit: [row: ModelConfig]
  toggle: [row: ModelConfig]
  copy: [value: string, label: string]
  sort: [key: ModelSortKey]
  resetFilters: []
}>()

function sortArrow(key: ModelSortKey): string {
  if (props.sortKey !== key) return '↕'
  return props.sortAsc ? '↑' : '↓'
}

function chipClass(tone: ExtraPriceChip['tone']): string {
  if (tone === 'amber') return 'm-pill--amber'
  if (tone === 'green') return 'm-pill--green'
  if (tone === 'teal') return 'm-pill--teal'
  return 'm-pill--muted'
}
</script>

<template>
  <div class="models-table-wrap">
    <div
      v-if="!rows.length"
      class="models-empty"
    >
      <p>{{ hasFilters ? '没有符合当前筛选条件的模型配置' : '暂无模型配置' }}</p>
      <el-button
        v-if="hasFilters"
        size="small"
        @click="emit('resetFilters')"
      >
        重置筛选条件
      </el-button>
    </div>

    <table
      v-else
      class="models-table"
    >
      <colgroup>
        <col class="col-name">
        <col class="col-status">
        <col class="col-provider">
        <col class="col-caps">
        <col class="col-main-price">
        <col class="col-extra-price">
        <col class="col-endpoint">
        <col class="col-sort">
        <col class="col-actions">
      </colgroup>
      <thead>
        <tr>
          <th scope="col">
            <button
              type="button"
              class="models-sort-btn"
              :class="{ 'is-sorted': sortKey === 'name' }"
              @click="emit('sort', 'name')"
            >
              <span>显示名称</span>
              <span class="models-sort-arrow">{{ sortArrow('name') }}</span>
            </button>
          </th>
          <th scope="col">
            状态
          </th>
          <th scope="col">
            厂商
          </th>
          <th scope="col">
            调用参数
          </th>
          <th
            scope="col"
            class="is-right"
          >
            <button
              type="button"
              class="models-sort-btn"
              :class="{ 'is-sorted': sortKey === 'price' }"
              @click="emit('sort', 'price')"
            >
              <span>生效单价（{{ unit === 'million' ? '¥/百万' : '元/千' }}）</span>
              <span class="models-sort-arrow">{{ sortArrow('price') }}</span>
            </button>
          </th>
          <th
            scope="col"
            class="is-right"
          >
            分时 · 缓存 · 联网价
          </th>
          <th scope="col">
            推理接入点
          </th>
          <th
            scope="col"
            class="is-right"
          >
            <button
              type="button"
              class="models-sort-btn"
              :class="{ 'is-sorted': sortKey === 'sort_order' }"
              @click="emit('sort', 'sort_order')"
            >
              <span>排序</span>
              <span class="models-sort-arrow">{{ sortArrow('sort_order') }}</span>
            </button>
          </th>
          <th
            scope="col"
            class="is-right"
          >
            操作
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.id"
          :class="{ 'is-disabled': !row.enabled }"
          @click="emit('view', row)"
        >
          <td>
            <button
              type="button"
              class="models-name-btn"
              :title="`${row.name}（模型 ID：${row.id}）`"
              @click.stop="emit('view', row)"
            >
              {{ row.name }}
            </button>
          </td>

          <td @click.stop>
            <span class="models-status-cell">
              <el-switch
                v-if="canWrite"
                size="small"
                :model-value="row.enabled"
                :loading="toggling === row.id"
                :disabled="Boolean(toggling && toggling !== row.id)"
                :aria-label="`${row.name} 启用开关`"
                @change="emit('toggle', row)"
              />
              <span
                v-if="canWrite"
                class="models-status-label"
                :class="{ 'is-off': !row.enabled }"
              >{{ row.enabled ? '启用' : '停用' }}</span>
              <span
                v-else
                class="m-pill m-pill--tag"
                :class="row.enabled ? 'm-pill--green' : 'm-pill--muted'"
              >{{ row.enabled ? '启用' : '停用' }}</span>
            </span>
          </td>

          <td>
            <span
              class="m-pill m-pill--tag"
              :class="row.provider === 'ark' ? 'm-pill--blue' : 'm-pill--teal'"
              :title="row.available === false ? '服务端尚未配置该厂商 API 密钥' : `${row.provider_name} 通道已就绪`"
            >
              {{ PROVIDER_LABELS[row.provider] ?? row.provider_name }}
            </span>
          </td>

          <td>
            <div
              class="models-caps-row"
              :title="row.rate_limit ? `限流说明：${row.rate_limit}` : '点击查看完整调用参数'"
            >
              <span
                class="m-pill m-pill--tag"
                :class="`m-pill--${serviceTierBadge(row.service_tier).tone}`"
              >
                {{ serviceTierBadge(row.service_tier).text }}
              </span>
              <span
                v-if="row.web_search"
                class="m-pill m-pill--tag m-pill--green"
              >
                联网
              </span>
              <span class="m-pill m-pill--tag m-pill--muted">
                {{ thinkingBadgeText(row) }}
              </span>
            </div>
          </td>

          <td
            class="is-right"
            :title="mainPriceDisplay(row, unit).tooltip"
          >
            <div class="models-price-line models-mono">
              <span
                v-if="mainPriceDisplay(row, unit).tag"
                class="m-pill m-pill--tag"
                :class="`m-pill--${mainPriceDisplay(row, unit).tagTone}`"
              >{{ mainPriceDisplay(row, unit).tag }}</span>
              <span class="models-price-main">{{ mainPriceDisplay(row, unit).pair }}</span>
            </div>
          </td>

          <td
            class="is-right"
            :title="listExtraPrices(row, unit).tooltip"
          >
            <div class="models-price-line models-mono">
              <span
                v-for="chip in listExtraPrices(row, unit).chips"
                :key="chip.text"
                class="m-pill m-pill--tag"
                :class="chipClass(chip.tone)"
              >{{ chip.text }}</span>
            </div>
          </td>

          <td @click.stop>
            <button
              type="button"
              class="models-ep-btn models-mono"
              :title="`点击复制完整接入点：${row.endpoint}`"
              @click="emit('copy', row.endpoint, '接入点')"
            >
              <span class="models-ep-btn__text">{{ shortEndpoint(row.endpoint) }}</span>
            </button>
          </td>

          <td
            class="is-right models-sort-num models-mono"
            title="下拉框排列顺序权重（数字越小越靠前）"
          >
            {{ row.sort_order }}
          </td>

          <td
            class="is-right"
            @click.stop
          >
            <span class="row-actions">
              <button
                type="button"
                class="row-action"
                @click="emit('view', row)"
              >
                查看
              </button>
              <button
                v-if="canWrite"
                type="button"
                class="row-action row-action--primary"
                @click="emit('edit', row)"
              >
                编辑
              </button>
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
