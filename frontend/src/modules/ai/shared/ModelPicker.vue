<script setup lang="ts">
import { computed } from 'vue'

import type { AiModel } from '@/api/ai'
import { priceText } from './aiText'

const props = withDefaults(defineProps<{
  models: AiModel[]
  label?: string
  allowEmpty?: boolean
  showThinking?: boolean
  size?: 'default' | 'small'
  disabled?: boolean
}>(), {
  label: '模型',
  allowEmpty: false,
  showThinking: true,
  size: 'default',
  disabled: false,
})
const model = defineModel<string>({ required: true })
const thinking = defineModel<boolean>('thinking', { default: false })
const current = computed(() => props.models.find(item => item.id === model.value))
</script>

<template>
  <div class="model-picker">
    <el-select
      v-model="model"
      :aria-label="label"
      :placeholder="allowEmpty ? '选择模型（上线前必选）' : '选择模型'"
      :clearable="allowEmpty"
      :size="size"
      :disabled="disabled"
      class="model-picker__select"
      :class="`model-picker__select--${size}`"
    >
      <el-option
        v-for="item in models"
        :key="item.id"
        :label="item.name"
        :value="item.id"
        :disabled="!item.available"
      >
        <span class="model-picker__option">
          <span>{{ item.name }}</span>
          <span
            v-if="!item.available"
            class="model-picker__off"
          >未配置密钥</span>
          <span
            v-else
            class="model-picker__price"
          >{{ priceText(item) }}</span>
        </span>
      </el-option>
    </el-select>
    <el-switch
      v-if="showThinking && current?.supports_thinking"
      v-model="thinking"
      active-text="深度思考"
    />
    <span
      v-if="current && !current.available"
      class="model-picker__off"
    >该模型的接口密钥未配置，暂不能使用</span>
  </div>
</template>

<style scoped>
.model-picker { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 14px; }
.model-picker__select { width: 280px; }
.model-picker__select--small { width: 200px; }
.model-picker__off { margin-left: 8px; color: var(--zt-warning-text); font-size: 12px; }
/* 下拉项：名称在左、参考价在右；下拉框按内容变宽，不截断价格。 */
.model-picker__option { display: flex; align-items: center; justify-content: space-between; gap: 24px; }
.model-picker__price { color: var(--zt-ink-500); font-size: 12px; font-variant-numeric: tabular-nums; }
</style>
