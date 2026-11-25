<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { createModelConfig, updateModelConfig, type ModelConfig } from '@/api/ai'
import { errorMessage, isStaleConflict } from '@/api/errors'
import { CONFLICT_TEXT } from '@/composables/useRecordEditor'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import ModelParamsCard from './ModelParamsCard.vue'
import ModelPricingCard from './ModelPricingCard.vue'
import {
  createEmptyDraft,
  draftFromModel,
  draftToBody,
  validateModelDraft,
  type ModelDraft,
} from './modelDraft'

const props = defineProps<{
  visible: boolean
  editing: ModelConfig | null
  arkReady: 'ready' | 'missing' | 'unknown'
  baiduReady: 'ready' | 'missing' | 'unknown'
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  saved: []
  conflict: []
}>()

const saving = ref(false)
const saveError = ref('')
const peakOpen = ref(false)
const draft = reactive<ModelDraft>(createEmptyDraft())

const openRef = computed({
  get: () => props.visible,
  set: (val: boolean) => emit('update:visible', val),
})

const guard = useUnsavedForm(openRef, () => draft, saving)
const isEdit = computed(() => Boolean(props.editing))
const selectedKeyState = computed(() => (draft.provider === 'ark' ? props.arkReady : props.baiduReady))

watch(() => props.visible, (open) => {
  if (!open) return
  const next = props.editing ? draftFromModel(props.editing) : createEmptyDraft()
  Object.assign(draft, next)
  peakOpen.value = Boolean(next.peak_input_price || next.peak_output_price || next.peak_cache_price)
  saveError.value = ''
  guard.markSaved(next)
}, { flush: 'sync' })

async function submit() {
  if (saving.value) return
  saveError.value = ''
  const problem = validateModelDraft(draft, isEdit.value)
  if (problem) {
    saveError.value = problem
    if (problem.includes('高峰')) peakOpen.value = true
    return
  }
  saving.value = true
  try {
    const body = draftToBody(draft)
    if (props.editing) {
      await updateModelConfig(props.editing.id, { ...body, id: props.editing.id, version: props.editing.version })
    } else {
      await createModelConfig(body)
    }
    guard.markSaved()
    ElMessage.success('已保存模型配置')
    emit('update:visible', false)
    emit('saved')
  } catch (error) {
    if (isStaleConflict(error)) {
      saveError.value = CONFLICT_TEXT
      emit('conflict')
    } else {
      saveError.value = errorMessage(error, '保存失败，请检查后重试')
    }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-drawer
    v-model="openRef"
    class="editor-overlay model-editor-drawer"
    size="680px"
    destroy-on-close
    :before-close="guard.beforeClose"
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
  >
    <template #header>
      <div class="me-head">
        <div class="me-head__row">
          <h2 class="me-head__title">
            {{ isEdit ? `编辑模型 · ${editing?.name}` : '新增模型配置' }}
          </h2>
          <span
            v-if="editing"
            class="m-pill m-pill--muted models-mono"
          >第 {{ editing.version }} 版</span>
        </div>
        <p class="me-head__sub">
          保留数据库「元 / 千 token」原值存储，右侧实时换算「¥ / 百万 token」防止录错小数位
        </p>
      </div>
    </template>

    <form
      class="me-form"
      novalidate
      @submit.prevent="submit"
    >
      <el-alert
        v-if="saveError"
        :title="saveError"
        type="error"
        show-icon
        :closable="false"
      />

      <!-- 01 基础身份与通道 -->
      <section class="me-card">
        <div class="me-card__head">
          <div class="me-card__title">
            <span class="m-pill m-pill--tag m-pill--blue models-mono">01</span>
            <span>基础身份与通道</span>
          </div>
          <span
            class="m-pill"
            :class="selectedKeyState === 'missing' ? 'm-pill--amber' : 'm-pill--green'"
          >
            {{ selectedKeyState === 'missing' ? '当前厂商服务端未配密钥' : '当前厂商服务端密钥已就绪' }}
          </span>
        </div>

        <div class="me-grid">
          <div class="me-field">
            <label
              class="me-label"
              for="me-id"
            >模型 ID <span class="me-req">*</span></label>
            <el-input
              id="me-id"
              v-model="draft.id"
              class="models-mono"
              :disabled="isEdit || saving"
              maxlength="64"
              placeholder="如 deepseek-v41-flash"
            />
            <span class="me-hint">{{ isEdit ? '已有模型的 ID 锁定只读，避免关联模板与历史账单断链' : '模板与批量任务按此 ID 引用，创建后不可修改' }}</span>
          </div>

          <div class="me-field">
            <label
              class="me-label"
              for="me-name"
            >显示名称 <span class="me-req">*</span></label>
            <el-input
              id="me-name"
              v-model="draft.name"
              :disabled="saving"
              maxlength="100"
              placeholder="如 字节-DeepSeek-V4.1-Flash经济版（不联网）"
            />
          </div>

          <div class="me-field">
            <label class="me-label">厂商通道 <span class="me-req">*</span></label>
            <el-select
              v-model="draft.provider"
              :disabled="saving"
            >
              <el-option
                value="ark"
                label="字节方舟"
              />
              <el-option
                value="baidu"
                label="百度千帆"
              />
            </el-select>
          </div>

          <div class="me-field">
            <label
              class="me-label"
              for="me-endpoint"
            >推理接入点 <span class="me-req">*</span></label>
            <el-input
              id="me-endpoint"
              v-model="draft.endpoint"
              class="models-mono"
              :disabled="saving"
              maxlength="128"
              :placeholder="draft.provider === 'ark' ? 'ep-...' : '如 deepseek-v4-flash'"
            />
            <span class="me-hint">{{ draft.provider === 'ark' ? '字节方舟填 ep- 开头的推理接入点 ID' : '百度千帆填官方模型编码（如 deepseek-v4-flash）' }}</span>
          </div>

          <div class="me-field">
            <label class="me-label">启用状态</label>
            <el-select
              v-model="draft.enabled"
              :disabled="saving"
            >
              <el-option
                :value="true"
                label="启用（出现在下拉列表）"
              />
              <el-option
                :value="false"
                label="停用（隐藏，已排队任务照常跑完）"
              />
            </el-select>
          </div>

          <div class="me-field">
            <label
              class="me-label"
              for="me-sort"
            >下拉排序权重</label>
            <el-input
              id="me-sort"
              v-model="draft.sort_order"
              class="models-mono"
              :disabled="saving"
              maxlength="6"
              placeholder="100"
            />
            <span class="me-hint">数字越小在下拉框里排得越靠前</span>
          </div>
        </div>
      </section>

      <!-- 02 调用参数与限流 -->
      <ModelParamsCard
        v-model:draft="draft"
        :saving="saving"
      />

      <!-- 03 计价配置 -->
      <ModelPricingCard
        v-model:draft="draft"
        v-model:peak-open="peakOpen"
        :saving="saving"
      />

      <!-- 04 编辑态只读系统留痕条 -->
      <div
        v-if="editing"
        class="me-audit models-mono"
      >
        <span>创建：{{ editing.created_by_name || '系统' }}（{{ editing.created_at }}）</span>
        <span>最近更新：{{ editing.updated_by_name || '系统' }}（{{ editing.updated_at }}）</span>
      </div>
    </form>

    <template #footer>
      <span
        v-if="guard.dirty.value"
        class="editor-dirty"
        role="status"
      >有未保存的修改</span>
      <span
        v-else
        class="me-foot-tip"
      >保存后模型下拉与计费立即按新配置执行</span>
      <el-button
        :disabled="saving"
        @click="guard.close"
      >
        取消
      </el-button>
      <el-button
        type="primary"
        :loading="saving"
        @click="submit"
      >
        保存配置
      </el-button>
    </template>
  </el-drawer>
</template>

<style scoped>
.me-head { display: flex; flex-direction: column; gap: 4px; }
.me-head__row { display: flex; align-items: center; gap: 8px; }
.me-head__title { margin: 0; color: var(--zt-ink-900); font-size: 16px; font-weight: 700; }
.me-head__sub { margin: 0; color: var(--zt-ink-500); font-size: 12px; font-weight: 400; }

.me-form {
  display: flex; flex-direction: column; gap: 16px;
  --el-input-bg-color: var(--zt-panel);
  --el-fill-color-blank: var(--zt-panel);
  --el-fill-color-light: var(--zt-surface-subtle);
}
.me-card {
  display: flex; flex-direction: column; gap: 14px;
  padding: 16px; border: 1px solid var(--zt-border); border-radius: 12px; background: var(--zt-panel);
}
.me-card__head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.me-card__title { display: flex; align-items: center; gap: 8px; color: var(--zt-ink-900); font-size: 14px; font-weight: 700; }

.me-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.me-field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.me-label { color: var(--zt-ink-900); font-size: 12.5px; font-weight: 600; line-height: 1.35; }
.me-req { margin-left: 2px; color: var(--zt-danger-text); }
.me-hint { color: var(--zt-ink-500); font-size: 11px; line-height: 1.4; }
.me-audit {
  display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 16px;
  padding: 10px 14px; border: 1px solid var(--zt-divider); border-radius: 8px;
  background: var(--zt-surface-subtle); color: var(--zt-ink-500); font-size: 11.5px;
}
.me-foot-tip { margin-right: auto; color: var(--zt-ink-500); font-size: 12px; }

@media (max-width: 600px) {
  .me-grid { grid-template-columns: 1fr; }
}
</style>
