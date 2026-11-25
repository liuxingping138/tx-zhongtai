<script setup lang="ts">
import { computed } from 'vue'

import type { ModelConfig } from '@/api/ai'
import {
  EFFORT_DETAIL_LABELS,
  formatPricePair,
  formatUnitPrice,
  plainDecimal,
  PROVIDER_LABELS,
  SERVICE_TIER_DETAIL_LABELS,
  THINKING_DETAIL_LABELS,
} from './modelView'

const props = defineProps<{
  model: ModelConfig | null
  canWrite: boolean
}>()

const emit = defineEmits<{
  close: []
  edit: [model: ModelConfig]
  copy: [value: string, label: string]
}>()

const open = computed({
  get: () => Boolean(props.model),
  set: (val: boolean) => { if (!val) emit('close') },
})

const effortDetail = computed(() => {
  const m = props.model
  if (!m) return ''
  if (m.thinking === 'disabled') return '思考关闭时不传'
  return EFFORT_DETAIL_LABELS[m.reasoning_effort] ?? (m.reasoning_effort || '按模型默认（不传）')
})

const cacheMillionText = computed(() => {
  const m = props.model
  if (!m?.cache_price) return '未单配（按此刻输入价计）'
  const base = formatUnitPrice(m.cache_price, 'million')
  return m.peak_cache_price ? `${base} / 峰 ${formatUnitPrice(m.peak_cache_price, 'million')}` : base
})

const cacheThousandText = computed(() => {
  const m = props.model
  if (!m?.cache_price) return '—'
  return m.peak_cache_price ? `${m.cache_price} / ${m.peak_cache_price} 元` : `${m.cache_price} 元`
})

const searchFeeText = computed(() => {
  const m = props.model
  if (!m) return ''
  const raw = plainDecimal(Number(m.search_price || '0'))
  return m.web_search ? `¥${raw} / 次（入库原值 ${raw} 元/次）` : `不联网（入库值 ${raw} 元/次）`
})
</script>

<template>
  <el-drawer
    v-model="open"
    class="editor-overlay model-detail-drawer"
    size="660px"
    destroy-on-close
  >
    <template #header>
      <div
        v-if="model"
        class="md-head"
      >
        <div class="md-head__titles">
          <h2 class="md-head__name">
            {{ model.name }}
          </h2>
          <span
            class="m-pill"
            :class="model.enabled ? 'm-pill--green' : 'm-pill--muted'"
          >{{ model.enabled ? '启用中' : '已停用' }}</span>
          <span
            class="m-pill"
            :class="model.provider === 'ark' ? 'm-pill--blue' : 'm-pill--teal'"
          >{{ PROVIDER_LABELS[model.provider] ?? model.provider_name }}</span>
          <span
            class="m-pill"
            :class="model.available === false ? 'm-pill--amber' : 'm-pill--green'"
          >{{ model.available === false ? '服务端未配密钥' : '密钥已就绪' }}</span>
        </div>
        <p class="md-head__sub">
          按「身份与通道 → 调用参数 → 多档计价矩阵 → 系统留痕」四层完整展示全部 27 项配置信息
        </p>
      </div>
    </template>

    <div
      v-if="model"
      class="md-body"
    >
      <!-- 01 基础身份与通道（完整对齐编辑抽屉第 1 组） -->
      <section class="md-section">
        <div class="md-section__head">
          <span class="m-pill m-pill--tag m-pill--blue models-mono">01</span>
          <h3 class="md-section__title">
            基础身份与通道
          </h3>
        </div>
        <dl class="md-table">
          <div class="md-cell">
            <dt>显示名称</dt>
            <dd class="is-strong">
              {{ model.name }}
            </dd>
          </div>
          <div class="md-cell">
            <dt>启用状态</dt>
            <dd :class="model.enabled ? 'is-ok' : 'is-muted'">
              {{ model.enabled ? '启用（出现在模板与批量下拉列表）' : '停用（下拉隐藏，已排队任务照常执行）' }}
            </dd>
          </div>
          <div class="md-cell">
            <dt>模型 ID</dt>
            <dd class="md-code-row models-mono">
              <span>{{ model.id }}</span>
              <button
                type="button"
                class="models-copy-btn"
                @click="emit('copy', model.id, '模型 ID')"
              >
                复制
              </button>
            </dd>
          </div>
          <div class="md-cell">
            <dt>推理接入点</dt>
            <dd class="md-code-row models-mono">
              <span>{{ model.endpoint }}</span>
              <button
                type="button"
                class="models-copy-btn"
                @click="emit('copy', model.endpoint, '接入点')"
              >
                复制
              </button>
            </dd>
          </div>
          <div class="md-cell">
            <dt>厂商通道</dt>
            <dd>{{ PROVIDER_LABELS[model.provider] ?? model.provider_name }}（{{ model.provider }}）</dd>
          </div>
          <div class="md-cell">
            <dt>下拉排序权重</dt>
            <dd class="models-mono">
              {{ model.sort_order }}（数字越小越靠前）
            </dd>
          </div>
        </dl>
      </section>

      <!-- 02 调用参数与限流（完整对齐编辑抽屉第 2 组） -->
      <section class="md-section">
        <div class="md-section__head">
          <span class="m-pill m-pill--tag m-pill--blue models-mono">02</span>
          <h3 class="md-section__title">
            调用参数与限流说明
          </h3>
        </div>
        <dl class="md-table">
          <div class="md-cell">
            <dt>联网搜索</dt>
            <dd :class="model.web_search ? 'is-ok' : ''">
              {{ model.web_search ? '开启联网（web_search）' : '不联网' }}
            </dd>
          </div>
          <div class="md-cell">
            <dt>服务档位</dt>
            <dd>{{ SERVICE_TIER_DETAIL_LABELS[model.service_tier] ?? (model.service_tier || '按模型默认（不传）') }}</dd>
          </div>
          <div class="md-cell">
            <dt>深度思考</dt>
            <dd>{{ THINKING_DETAIL_LABELS[model.thinking] ?? (model.thinking || '按模型默认（不传）') }}</dd>
          </div>
          <div class="md-cell">
            <dt>思考强度</dt>
            <dd>{{ effortDetail }}</dd>
          </div>
          <div class="md-cell is-full">
            <dt>限流说明</dt>
            <dd>{{ model.rate_limit || '未填写（仅作运维配额记录，不限制批量并发）' }}</dd>
          </div>
        </dl>
      </section>

      <!-- 03 多档计价矩阵（完整对齐编辑抽屉第 3 组全部 10 个计价字段） -->
      <section class="md-section">
        <div class="md-section__head">
          <span class="m-pill m-pill--tag m-pill--blue models-mono">03</span>
          <h3 class="md-section__title">
            多档计价矩阵（百万 token 直观值 ↔ 千 token 入库原值）
          </h3>
        </div>
        <div class="md-matrix-wrap">
          <table class="md-matrix models-mono">
            <thead>
              <tr>
                <th>Token 计费档位</th>
                <th class="is-right">
                  按百万 token（直观）
                </th>
                <th class="is-right">
                  按千 token（入库原值）
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td class="md-matrix__label">
                  常规 / 空闲时段（输入 / 输出）
                </td>
                <td class="is-right md-matrix__strong">
                  {{ formatPricePair(model.input_price, model.output_price, 'million') }}
                </td>
                <td class="is-right md-matrix__muted">
                  {{ formatPricePair(model.input_price, model.output_price, 'thousand') }} 元
                </td>
              </tr>
              <tr>
                <td class="md-matrix__label">
                  低优异步档 flex（输入 / 输出）
                  <span
                    v-if="model.service_tier === 'flex' && model.flex_input_price"
                    class="m-pill m-pill--tag m-pill--amber"
                  >当前生效</span>
                </td>
                <td class="is-right md-matrix__strong">
                  {{ model.flex_input_price ? formatPricePair(model.flex_input_price, model.flex_output_price, 'million') : '—' }}
                </td>
                <td class="is-right md-matrix__muted">
                  {{ model.flex_input_price ? `${formatPricePair(model.flex_input_price, model.flex_output_price, 'thousand')} 元` : '未配置' }}
                </td>
              </tr>
              <tr>
                <td class="md-matrix__label">
                  工作日高峰时段
                  <span class="md-matrix__note models-mono">
                    {{ model.peak_hours ? `(${model.peak_hours})` : '（未设分时）' }}
                  </span>
                </td>
                <td class="is-right md-matrix__warn">
                  {{ model.peak_input_price ? formatPricePair(model.peak_input_price, model.peak_output_price, 'million') : '—' }}
                </td>
                <td class="is-right md-matrix__muted">
                  {{ model.peak_input_price ? `${formatPricePair(model.peak_input_price, model.peak_output_price, 'thousand')} 元` : '全天同价' }}
                </td>
              </tr>
              <tr>
                <td class="md-matrix__label">
                  上下文缓存命中输入（平时 / 高峰）
                </td>
                <td class="is-right md-matrix__ok">
                  {{ cacheMillionText }}
                </td>
                <td class="is-right md-matrix__muted">
                  {{ cacheThousandText }}
                </td>
              </tr>
            </tbody>
          </table>
          <div class="md-search-bar">
            <span class="md-search-bar__k">联网搜索按次附加费</span>
            <strong class="models-mono">{{ searchFeeText }}</strong>
          </div>
        </div>
      </section>

      <!-- 04 系统留痕信息（补齐创建人、创建时间、更新人、更新时间与乐观锁版本号） -->
      <section class="md-section">
        <div class="md-section__head">
          <span class="m-pill m-pill--tag m-pill--muted models-mono">04</span>
          <h3 class="md-section__title">
            系统留痕信息
          </h3>
        </div>
        <dl class="md-table">
          <div class="md-cell">
            <dt>创建记录</dt>
            <dd class="models-mono">
              {{ model.created_by_name || '系统' }} · {{ model.created_at || '—' }}
            </dd>
          </div>
          <div class="md-cell">
            <dt>最近更新</dt>
            <dd class="models-mono">
              {{ model.updated_by_name || '系统' }} · {{ model.updated_at || '—' }}
            </dd>
          </div>
          <div class="md-cell is-full">
            <dt>配置版本</dt>
            <dd class="models-mono">
              第 {{ model.version }} 版（并发修改时按版本号防覆盖保护）
            </dd>
          </div>
        </dl>
      </section>
    </div>

    <template #footer>
      <el-button @click="emit('close')">
        关闭
      </el-button>
      <el-button
        v-if="canWrite && model"
        type="primary"
        @click="emit('edit', model)"
      >
        编辑配置
      </el-button>
    </template>
  </el-drawer>
</template>

<style scoped>
.md-head { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.md-head__titles { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.md-head__name { margin: 0; color: var(--zt-ink-900); font-size: 16px; font-weight: 700; }
.md-head__sub { margin: 0; color: var(--zt-ink-500); font-size: 12px; font-weight: 400; }

.md-body { display: flex; flex-direction: column; gap: 18px; }
.md-section { display: flex; flex-direction: column; gap: 8px; }
.md-section__head { display: flex; align-items: center; gap: 8px; }
.md-section__title { margin: 0; color: var(--zt-ink-900); font-size: 13.5px; font-weight: 700; }

/* 标准双列带边框字段表（左灰底标签、右值，长字段占整行） */
.md-table {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin: 0;
  border: 1px solid var(--zt-border);
  border-radius: 10px;
  overflow: hidden;
  font-size: 12.5px;
}
.md-cell {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  border-bottom: 1px solid var(--zt-divider);
  border-right: 1px solid var(--zt-divider);
}
.md-cell:nth-child(2n) { border-right: 0; }
.md-cell.is-full { grid-column: span 2; border-right: 0; }
.md-table > .md-cell:last-child,
.md-table > .md-cell:nth-last-child(2):nth-child(odd):not(.is-full) { border-bottom: 0; }

.md-cell dt {
  display: flex; align-items: center;
  padding: 9px 12px; background: var(--zt-surface-subtle); border-right: 1px solid var(--zt-divider);
  color: var(--zt-ink-500); font-weight: 500;
}
.md-cell dd {
  display: flex; align-items: center; gap: 6px; margin: 0; padding: 9px 12px;
  background: var(--zt-panel); color: var(--zt-ink-900); word-break: break-word;
}
.md-cell dd.is-strong { font-weight: 650; }
.md-cell dd.is-ok { color: var(--zt-success-text); font-weight: 600; }
.md-cell dd.is-muted { color: var(--zt-ink-500); }
.md-code-row { justify-content: space-between; }

.md-matrix-wrap { border: 1px solid var(--zt-border); border-radius: 10px; overflow: hidden; }
.md-matrix { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.md-matrix th {
  padding: 9px 12px; background: var(--zt-table-head); border-bottom: 1px solid var(--zt-border);
  color: var(--zt-ink-500); font-family: var(--zt-font); font-size: 12px; font-weight: 600; text-align: left;
}
.md-matrix td { padding: 9px 12px; border-bottom: 1px solid var(--zt-divider); color: var(--zt-ink-700); }
.md-matrix th.is-right, .md-matrix td.is-right { text-align: right; }
.md-matrix__label { font-family: var(--zt-font); font-weight: 500; color: var(--zt-ink-900); }
.md-matrix__note { margin-left: 4px; color: var(--zt-ink-500); font-size: 11.5px; }
.md-matrix__strong { color: var(--zt-ink-900); font-weight: 700; }
.md-matrix__muted { color: var(--zt-ink-500); }
.md-matrix__warn { color: var(--zt-warning-text); font-weight: 700; }
.md-matrix__ok { color: var(--zt-success-text); font-weight: 700; }

.md-search-bar {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 9px 12px; background: var(--zt-surface-subtle); font-size: 12.5px; color: var(--zt-ink-900);
}
.md-search-bar__k { color: var(--zt-ink-500); font-weight: 500; }

@media (max-width: 600px) {
  .md-table { grid-template-columns: 1fr; }
  .md-cell, .md-cell.is-full { grid-column: span 1; border-right: 0; border-bottom: 1px solid var(--zt-divider); }
  .md-table > .md-cell:last-child { border-bottom: 0; }
}
</style>
