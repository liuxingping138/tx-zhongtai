<script setup lang="ts">
import { ref } from 'vue'

import { searchScenarioPaths, type ScenarioPath } from '@/api/codebook'
import { pathLabel } from '@/modules/policy/scenario-candidates/candidates'

/**
 * 从行业场景码表里选一条路径（按名称搜，按客群去重）。合并到已有场景、改某一行的场景都用它，
 * 不手打六级名称：打错一个字就又成了新场景。
 */
const props = withDefaults(defineProps<{
  modelValue: ScenarioPath | null
  /** 只在这个一级行业下找；不传就全码表找 */
  industryL1?: string
  placeholder?: string
}>(), { industryL1: '', placeholder: '输入场景名称搜码表，如「航站楼」' })
const emit = defineEmits<{ 'update:modelValue': [value: ScenarioPath | null] }>()

const options = ref<ScenarioPath[]>(props.modelValue ? [props.modelValue] : [])
const searching = ref(false)
const failed = ref(false)
let sequence = 0

async function search(keyword: string) {
  const text = keyword.trim()
  if (!text) return
  const current = ++sequence
  searching.value = true
  failed.value = false
  try {
    const found = await searchScenarioPaths(text, props.industryL1)
    if (current === sequence) options.value = found.items
  } catch {
    if (current === sequence) {
      options.value = []
      failed.value = true
    }
  } finally {
    if (current === sequence) searching.value = false
  }
}

function keyOf(path: ScenarioPath): string {
  return `${path.industry_scenario_code}|${pathLabel(path)}`
}

function pick(key: string) {
  emit('update:modelValue', options.value.find(path => keyOf(path) === key) ?? null)
}
</script>

<template>
  <el-select
    class="scenario-picker"
    :model-value="modelValue ? keyOf(modelValue) : ''"
    filterable
    remote
    clearable
    :remote-method="search"
    :loading="searching"
    :placeholder="placeholder"
    :no-data-text="failed ? '码表暂时搜不到，请稍后再试' : '码表里没有包含这个词的场景'"
    @update:model-value="pick"
  >
    <el-option
      v-for="path in options"
      :key="keyOf(path)"
      :value="keyOf(path)"
      :label="pathLabel(path)"
    />
  </el-select>
</template>

<style scoped>
.scenario-picker {
  width: 100%;
}
</style>
