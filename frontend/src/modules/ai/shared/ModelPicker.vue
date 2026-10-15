<script setup lang="ts">
import { computed } from 'vue'

import type { AiModel } from '@/api/ai'

const props = withDefaults(defineProps<{ models: AiModel[]; label?: string; allowEmpty?: boolean; showThinking?: boolean }>(), {
  label: '模型',
  allowEmpty: false,
  showThinking: true,
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
      :placeholder="allowEmpty ? '未指定（运行时选择）' : '选择模型'"
      :clearable="allowEmpty"
      class="model-picker__select"
    >
      <el-option
        v-for="item in models"
        :key="item.id"
        :label="item.name"
        :value="item.id"
        :disabled="!item.available"
      >
        <span>{{ item.name }}</span>
        <span
          v-if="!item.available"
          class="model-picker__off"
        >未配置密钥</span>
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
.model-picker__off { margin-left: 8px; color: var(--el-color-warning); font-size: 12px; }
</style>
