<script setup lang="ts">
import { computed } from 'vue'

import ModelPriceInput from './ModelPriceInput.vue'
import type { ModelDraft } from './modelDraft'

const draft = defineModel<ModelDraft>('draft', { required: true })
const peakOpen = defineModel<boolean>('peakOpen', { required: true })

defineProps<{
  saving: boolean
}>()

const isFlex = computed(() => draft.value.service_tier === 'flex')
const hasPeak = computed(() => Boolean(
  draft.value.peak_input_price.trim()
  || draft.value.peak_output_price.trim()
  || draft.value.peak_cache_price.trim(),
))

function onTogglePeak(event: Event) {
  peakOpen.value = (event.currentTarget as HTMLDetailsElement).open
}
</script>

<template>
  <section class="mp-card">
    <div class="mp-card__head">
      <div class="mp-card__title">
        <span class="m-pill m-pill--tag m-pill--blue models-mono">03</span>
        <span>计价配置（入库单位：元 / 千 token）</span>
      </div>
      <span class="m-pill m-pill--green">防呆保护：输入时自动换算百万 token 单价</span>
    </div>

    <div class="mp-grid">
      <ModelPriceInput
        v-model="draft.input_price"
        input-id="me-p-in"
        label="常规输入单价"
        required
        :disabled="saving"
        placeholder="必填，如 0.0008"
      />
      <ModelPriceInput
        v-model="draft.output_price"
        input-id="me-p-out"
        label="常规输出单价"
        required
        :disabled="saving"
        placeholder="必填，如 0.0032"
      />
      <ModelPriceInput
        v-model="draft.cache_price"
        input-id="me-p-cache"
        label="上下文缓存命中单价（选填）"
        :disabled="saving"
        placeholder="选填，留空按输入价计"
      />

      <div class="mp-field">
        <label
          class="mp-label"
          for="me-p-search"
        >
          联网搜索单价（元 / 次）
          <span
            v-if="!draft.web_search"
            class="mp-lock-note"
          >（不联网已自动锁定为 0）</span>
        </label>
        <div class="mp-search-wrap">
          <el-input
            id="me-p-search"
            v-model="draft.search_price"
            class="models-mono"
            :disabled="!draft.web_search || saving"
            maxlength="20"
            placeholder="0"
          />
          <span class="m-pill m-pill--tag m-pill--muted mp-search-badge models-mono">按次计费</span>
        </div>
      </div>
    </div>

    <div
      class="mp-subbox"
      :class="{ 'is-dimmed': !isFlex }"
    >
      <div class="mp-subbox__head">
        <span class="mp-subbox__title">低优档单价（flex）</span>
        <span
          class="m-pill"
          :class="isFlex ? 'm-pill--amber' : 'm-pill--muted'"
        >
          {{ isFlex ? '当前已选低优 flex 档（优先生效）' : '当前未选低优档（可留空）' }}
        </span>
      </div>
      <div class="mp-grid">
        <ModelPriceInput
          v-model="draft.flex_input_price"
          input-id="me-p-flex-in"
          label="低优输入单价"
          :required="isFlex"
          :disabled="saving"
          placeholder="如 0.0015"
        />
        <ModelPriceInput
          v-model="draft.flex_output_price"
          input-id="me-p-flex-out"
          label="低优输出单价"
          :required="isFlex"
          :disabled="saving"
          placeholder="如 0.0045"
        />
      </div>
    </div>

    <details
      class="mp-subbox mp-details"
      :open="peakOpen"
      @toggle="onTogglePeak"
    >
      <summary class="mp-details__summary">
        <span class="mp-subbox__title">工作日高峰分时计价（选填 · 如 V4.1-Flash 经济版）</span>
        <span
          class="m-pill"
          :class="hasPeak ? 'm-pill--amber' : 'm-pill--muted'"
        >
          {{ hasPeak ? '已配置工作日高峰分时价' : '未配置分时价（全天按常规价）' }}
        </span>
      </summary>
      <div class="mp-grid mp-details__body">
        <ModelPriceInput
          v-model="draft.peak_input_price"
          input-id="me-p-peak-in"
          label="高峰输入单价"
          :disabled="saving"
          placeholder="选填，如 0.0016"
        />
        <ModelPriceInput
          v-model="draft.peak_output_price"
          input-id="me-p-peak-out"
          label="高峰输出单价"
          :disabled="saving"
          placeholder="选填，如 0.0064"
        />
        <ModelPriceInput
          v-model="draft.peak_cache_price"
          input-id="me-p-peak-cache"
          label="高峰缓存单价"
          :disabled="saving"
          placeholder="选填，需先填平时缓存价"
        />
        <div class="mp-field">
          <label
            class="mp-label"
            for="me-peak-hours"
          >工作日高峰时段（北京时间）</label>
          <el-input
            id="me-peak-hours"
            v-model="draft.peak_hours"
            class="models-mono"
            :disabled="saving"
            maxlength="100"
            placeholder="09:00-12:00,14:00-18:00"
          />
        </div>
      </div>
    </details>
  </section>
</template>

<style scoped>
.mp-card {
  display: flex; flex-direction: column; gap: 14px;
  padding: 16px; border: 1px solid var(--zt-border); border-radius: 12px; background: var(--zt-panel);
}
.mp-card__head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.mp-card__title { display: flex; align-items: center; gap: 8px; color: var(--zt-ink-900); font-size: 14px; font-weight: 700; }
.mp-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.mp-field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.mp-label { color: var(--zt-ink-900); font-size: 12.5px; font-weight: 600; line-height: 1.35; }
.mp-lock-note { font-weight: 400; color: var(--zt-ink-500); font-size: 11.5px; }

.mp-search-wrap { position: relative; display: flex; align-items: center; }
.mp-search-wrap :deep(.el-input__inner) { padding-right: 76px; }
.mp-search-badge { position: absolute; right: 8px; pointer-events: none; }

.mp-subbox {
  display: flex; flex-direction: column; gap: 12px;
  padding: 14px; border: 1px solid var(--zt-border); border-radius: 10px;
  background: var(--zt-surface-subtle); transition: opacity 0.16s ease;
}
.mp-subbox.is-dimmed { opacity: 0.78; }
.mp-subbox__head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.mp-subbox__title { color: var(--zt-ink-900); font-size: 12.5px; font-weight: 650; }

.mp-details__summary {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  cursor: pointer; list-style: none; user-select: none;
}
.mp-details__summary::-webkit-details-marker { display: none; }
.mp-details__body { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--zt-border); }

@media (max-width: 600px) {
  .mp-grid { grid-template-columns: 1fr; }
}
</style>
