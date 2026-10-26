<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { listAiTemplates, updateAiTask, type AiTask, type OnlineTemplate } from '@/api/aiTagging'
import { updateJob, type ScheduledJob } from '@/api/scheduler'
import { errorMessage } from '@/api/errors'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { TASK_INTRO, formatYuan } from './aiTagging'

/** 一个任务的设置：每日计划；打标任务再加模板、每批条数、正文长度、每日上限，类型判断还有起始采集日期。 */
const emit = defineEmits<{ saved: [] }>()
const visible = ref(false)
const saving = ref(false)
const error = ref('')
const job = ref<ScheduledJob | null>(null)
const task = ref<AiTask | null>(null)
const templates = ref<OnlineTemplate[]>([])
const templatesError = ref('')
const schedule = reactive({ enabled: false, daily_time: '10:00' })
const ai = reactive({ prompt_id: '', batch_size: 10, content_max_chars: 0, daily_cost_limit: '0', cursor_date: '' })
const unsaved = useUnsavedForm(visible, () => ({ schedule, ai: task.value ? ai : null }), saving)

// 放进这个任务写不回表的模板置灰并写原因；选着的模板被下线后不在上线列表里，也显示成一项，免得露出一串 ID。
const templateOptions = computed(() => {
  const code = task.value?.code
  const options = templates.value.map(item => {
    const errors = code ? item.checks?.[code]?.errors ?? [] : []
    return { value: item.prompt_id, label: `${item.title}（第 ${item.release_no} 版）`, disabled: errors.length > 0, reason: errors[0] ?? '' }
  })
  if (ai.prompt_id && !options.some(item => item.value === ai.prompt_id)) {
    options.unshift({ value: ai.prompt_id, label: '已下线的模板，请重新选择', disabled: false, reason: '' })
  }
  return options
})
/** 选着的模板放进这个任务的问题：必须改的和提醒都列在下拉框下面。 */
const chosenCheck = computed(() => {
  const code = task.value?.code
  const chosen = templates.value.find(item => item.prompt_id === ai.prompt_id)
  return code && chosen ? chosen.checks?.[code] ?? null : null
})

/** 先填好表单再打开：未保存提示以打开那一刻的内容为基线。 */
function open(target: ScheduledJob, aiTask: AiTask | null): void {
  job.value = target
  task.value = aiTask
  Object.assign(schedule, { enabled: target.enabled, daily_time: target.daily_time })
  if (aiTask) {
    const { prompt_id, batch_size, content_max_chars, daily_cost_limit, cursor_date } = aiTask
    Object.assign(ai, { prompt_id, batch_size, content_max_chars, daily_cost_limit, cursor_date })
    void loadTemplates()
  }
  error.value = ''
  visible.value = true
}

async function loadTemplates(): Promise<void> {
  templatesError.value = ''
  try {
    const data = await listAiTemplates()
    templates.value = data.items
    templatesError.value = data.error
  } catch (cause) {
    templatesError.value = errorMessage(cause, '上线模板加载失败')
  }
}

/** 0 = 全文；切到截取时给个常用的起点，再按需调。 */
function setContentMode(mode: string | number | boolean | undefined): void {
  ai.content_max_chars = mode === 'all' ? 0 : 15000
}

async function saveTask(current: AiTask): Promise<void> {
  task.value = await updateAiTask(current.code, { ...ai, daily_cost_limit: String(ai.daily_cost_limit), version: current.version })
}

async function saveSchedule(current: ScheduledJob): Promise<void> {
  if (schedule.enabled === current.enabled && schedule.daily_time === current.daily_time) return
  await updateJob(current.code, { ...schedule, version: current.version }, { base: current.base })
}

async function save(): Promise<void> {
  if (!job.value || saving.value) return
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(schedule.daily_time)) {
    error.value = '请选择有效的每日执行时刻'
    return
  }
  saving.value = true
  error.value = ''
  try {
    if (task.value) await saveTask(task.value)
    await saveSchedule(job.value)
    unsaved.markSaved()
    visible.value = false
    ElMessage.success('设置已保存，下次执行按新设置')
    emit('saved')
  } catch (cause) {
    error.value = errorMessage(cause, '保存失败，请重试')
  } finally {
    saving.value = false
  }
}

defineExpose({ open })
</script>

<template>
  <el-drawer
    v-model="visible"
    :title="`设置 · ${job?.name ?? ''}`"
    size="min(560px, 96vw)"
    :before-close="unsaved.beforeClose"
    :close-on-click-modal="false"
  >
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />
    <!-- novalidate：数字框的合法值是「最小值 + 步长的整数倍」，浏览器会静默拦下 10、1000 这类提交；范围由后端校验并给中文提示。 -->
    <el-form
      label-position="top"
      novalidate
      class="job-settings"
      :disabled="saving"
      @submit.prevent="save"
    >
      <template v-if="task">
        <p class="job-settings__intro">
          {{ TASK_INTRO[task.code] }}
        </p>
        <el-form-item label="使用的模板">
          <el-select
            v-model="ai.prompt_id"
            clearable
            popper-class="job-settings-popper"
            :placeholder="templates.length ? '选择已上线的政策类模板' : '还没有已上线的政策类模板'"
          >
            <el-option
              v-for="item in templateOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
              :disabled="item.disabled"
            >
              <span>{{ item.label }}</span>
              <span
                v-if="item.reason"
                class="job-settings__option-reason"
              >不能用：{{ item.reason }}</span>
            </el-option>
          </el-select>
          <span
            class="job-settings__hint"
            :class="{ 'is-error': templatesError }"
          >{{ templatesError || '只列政策类、已上线的模板；用的是上线时冻结的那一版' }}</span>
          <ul
            v-if="chosenCheck && (chosenCheck.errors.length || chosenCheck.warnings.length)"
            class="job-settings__checks"
          >
            <li
              v-for="text in chosenCheck.errors"
              :key="text"
              class="is-error"
            >
              {{ text }}
            </li>
            <li
              v-for="text in chosenCheck.warnings"
              :key="text"
            >
              {{ text }}
            </li>
          </ul>
        </el-form-item>
        <el-form-item label="每批条数">
          <el-input-number
            v-model="ai.batch_size"
            :min="1"
            :max="20000"
            :step="10"
            controls-position="right"
          />
          <span class="job-settings__hint">{{ task.code === 'type' ? '一次执行读这么多条源政策' : '一次执行最多处理这么多条待办政策' }}；先用几十条试跑</span>
        </el-form-item>
        <el-form-item label="发给模型的正文">
          <el-radio-group
            :model-value="ai.content_max_chars ? 'cut' : 'all'"
            @update:model-value="setContentMode"
          >
            <el-radio value="all">
              全文
            </el-radio>
            <el-radio value="cut">
              截取前
            </el-radio>
          </el-radio-group>
          <el-input-number
            v-if="ai.content_max_chars"
            v-model="ai.content_max_chars"
            :min="500"
            :max="200000"
            :step="1000"
            controls-position="right"
            aria-label="截取字数"
          />
          <span class="job-settings__hint">{{ ai.content_max_chars ? '超出部分不发给模型，省费用但可能漏掉后文' : '整页正文全部发给模型，费用按实际长度算' }}</span>
        </el-form-item>
        <el-form-item label="每日费用上限（元）">
          <el-input
            v-model="ai.daily_cost_limit"
            inputmode="decimal"
          />
          <span class="job-settings__hint">今天已花 {{ formatYuan(task.spent_today) }}，本月 {{ formatYuan(task.spent_month) }}；到上限就停，剩下的明天接着做，按低优档计价</span>
        </el-form-item>
        <el-form-item
          v-if="task.code === 'type'"
          label="从哪天的采集数据开始"
        >
          <el-date-picker
            v-model="ai.cursor_date"
            type="date"
            value-format="YYYY-MM-DD"
            :clearable="false"
          />
          <span class="job-settings__hint">当前读到：{{ task.cursor_date || '—' }} {{ task.cursor_content_id || '（当日第一条）' }}。改日期就从那天第一条重新读，要补历史就往前调</span>
        </el-form-item>
        <h3 class="job-settings__section">
          每日计划
        </h3>
      </template>
      <el-form-item label="每日自动执行">
        <el-switch
          v-model="schedule.enabled"
          active-text="启用"
          inactive-text="停用"
        />
      </el-form-item>
      <el-form-item label="执行时刻（北京时间）">
        <el-time-select
          v-model="schedule.daily_time"
          start="00:00"
          step="00:10"
          end="23:50"
          :clearable="false"
          placeholder="选择执行时刻"
        />
      </el-form-item>
      <p class="job-settings__hint">
        停用会取消排队和等待重试的任务，正在执行的批次会继续完成。停用期间仍可手动执行。
      </p>
    </el-form>
    <template #footer>
      <el-button
        :disabled="saving"
        @click="unsaved.close"
      >
        取消
      </el-button><el-button
        type="primary"
        :loading="saving"
        @click="save"
      >
        保存设置
      </el-button>
    </template>
  </el-drawer>
</template>

<style scoped>
.job-settings :deep(.el-select), .job-settings :deep(.el-input-number), .job-settings :deep(.el-date-editor) { width: 100%; }
.job-settings :deep(.el-radio-group) { margin-right: 12px; }
.job-settings :deep(.el-radio-group + .el-input-number) { width: 180px; }
.job-settings__intro { margin: 0 0 18px; padding: 10px 12px; border-radius: 4px; background: var(--zt-soft); color: var(--zt-ink-700); font-size: 13px; line-height: 1.7; }
.job-settings__hint { display: block; width: 100%; color: var(--zt-ink-500); font-size: 12px; line-height: 1.6; }
.job-settings__hint.is-error { color: var(--el-color-danger); }
.job-settings__checks { width: 100%; margin: 6px 0 0; padding: 8px 12px 8px 26px; border-radius: 4px; background: #fdf6ec; color: #8a5a14; font-size: 12px; line-height: 1.6; }
.job-settings__checks .is-error { color: var(--el-color-danger); }
.job-settings__section { margin: 24px 0 12px; padding-top: 16px; border-top: 1px solid var(--zt-border); color: var(--zt-ink-900); font-size: 14px; font-weight: 600; }
</style>

<style>
/* 下拉列表挂在 body 上，scoped 样式够不着：不能用的模板多一行原因，选项要能撑高。 */
.job-settings-popper .el-select-dropdown__item:has(.job-settings__option-reason) { height: auto; padding-top: 6px; padding-bottom: 6px; line-height: 1.5; }
.job-settings-popper .job-settings__option-reason { display: block; max-width: 460px; color: var(--el-color-danger); font-size: 12px; line-height: 1.4; white-space: normal; }
</style>
