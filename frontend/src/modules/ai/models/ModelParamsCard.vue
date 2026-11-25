<script setup lang="ts">
import { computed } from 'vue'

import type { ModelDraft } from './modelDraft'

const draft = defineModel<ModelDraft>('draft', { required: true })

defineProps<{
  saving: boolean
}>()

const effortOff = computed(() => draft.value.thinking === 'disabled')

function onWebChange(enabled: boolean) {
  if (!enabled) draft.value.search_price = '0'
}

function onThinkingChange(val: string) {
  if (val === 'disabled') draft.value.reasoning_effort = ''
}
</script>

<template>
  <section class="mc-card">
    <div class="mc-card__head">
      <div class="mc-card__title">
        <span class="m-pill m-pill--tag m-pill--blue models-mono">02</span>
        <span>调用参数与限流说明</span>
      </div>
      <span class="mc-card__note">切换联网、档位或思考模式会自动联动下方计价项</span>
    </div>

    <div class="mc-grid">
      <div class="mc-field">
        <label class="mc-label">联网搜索</label>
        <el-select
          v-model="draft.web_search"
          :disabled="saving"
          @change="onWebChange"
        >
          <el-option
            :value="false"
            label="不联网"
          />
          <el-option
            :value="true"
            label="联网"
          />
        </el-select>
      </div>

      <div class="mc-field">
        <label class="mc-label">服务档位（service_tier）</label>
        <el-select
          v-model="draft.service_tier"
          :disabled="saving"
        >
          <el-option
            value=""
            label="按模型默认（不传）"
          />
          <el-option
            value="flex"
            label="低优（flex · 价格更低，适合批量异步）"
          />
          <el-option
            value="auto"
            label="常规（auto）"
          />
        </el-select>
      </div>

      <div class="mc-field">
        <label class="mc-label">深度思考</label>
        <el-select
          v-model="draft.thinking"
          :disabled="saving"
          @change="onThinkingChange"
        >
          <el-option
            value="enabled"
            label="开启"
          />
          <el-option
            value="switch"
            label="提问时可选（千帆开关控制）"
          />
          <el-option
            value="disabled"
            label="关闭"
          />
          <el-option
            value=""
            label="按模型默认"
          />
        </el-select>
      </div>

      <div class="mc-field">
        <label class="mc-label">
          思考强度
          <span
            v-if="effortOff"
            class="mc-lock-note"
          >（思考关闭时不传）</span>
        </label>
        <el-select
          v-model="draft.reasoning_effort"
          :disabled="effortOff || saving"
        >
          <el-option
            value="low"
            label="低（low · 省输出 token）"
          />
          <el-option
            value="high"
            label="高（high）"
          />
          <el-option
            value="max"
            label="最高（max）"
          />
          <el-option
            value=""
            label="按模型默认"
          />
        </el-select>
      </div>

      <div class="mc-field is-span-2">
        <label
          class="mc-label"
          for="me-rate"
        >限流说明（选填备注）</label>
        <el-input
          id="me-rate"
          v-model="draft.rate_limit"
          :disabled="saving"
          maxlength="500"
          placeholder="如：3000 RPM、5000000 TPM（仅做运维记录，不控制并发）"
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
.mc-card {
  display: flex; flex-direction: column; gap: 14px;
  padding: 16px; border: 1px solid var(--zt-border); border-radius: 12px; background: var(--zt-panel);
}
.mc-card__head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.mc-card__title { display: flex; align-items: center; gap: 8px; color: var(--zt-ink-900); font-size: 14px; font-weight: 700; }
.mc-card__note { color: var(--zt-ink-500); font-size: 12px; }
.mc-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.mc-field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.mc-field.is-span-2 { grid-column: span 2; }
.mc-label { color: var(--zt-ink-900); font-size: 12.5px; font-weight: 600; line-height: 1.35; }
.mc-lock-note { font-weight: 400; color: var(--zt-ink-500); font-size: 11.5px; }

@media (max-width: 600px) {
  .mc-grid { grid-template-columns: 1fr; }
  .mc-field.is-span-2 { grid-column: span 1; }
}
</style>
