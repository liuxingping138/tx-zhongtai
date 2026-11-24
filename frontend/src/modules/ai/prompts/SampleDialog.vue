<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { savePromptTestRows, type PromptTemplate } from '@/api/ai'
import { getTaggingSamples, type AiTaskCode, type ContractTask } from '@/api/aiTagging'
import { errorMessage } from '@/api/errors'
import { guessTask } from './taskFit'

/** 从数据库取测试数据：和正式打标交给模板的一模一样，存成模板的测试 Excel（替换原来的）。 */
const props = defineProps<{ template: PromptTemplate; tasks: ContractTask[]; provinces?: string[]; industries?: string[] }>()
const emit = defineEmits<{ done: [template: PromptTemplate] }>()
const open = defineModel<boolean>({ required: true })

const HINTS: Record<AiTaskCode, string> = {
  type: '取这一天采集的源政策，和「政策类型判断」按天读的一样。',
  interpret: '取最近被判为「需要解读」（含信息化建设类）的政策，要先跑过政策类型判断才有。',
  opportunity: '取最近解读过的政策，按「一级行业 + 一级场景」逐组展开，提供 @【一级行业】、@【一级场景】、@【政策正文】 等列，与定时任务完全一致。',
  scenario: '取「新增场景审核」里待审的场景，带上 @【同行业已有场景】：码表里同一个一级行业下的全部场景。',
  enrich: '取码表里待补描述的新增场景，带上 @【上级场景描述】 @【同级场景示例】当范文。',
}
const yesterday = () => new Date(Date.now() - 86_400_000).toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
const task = ref<AiTaskCode>('type')
const day = ref(yesterday())
const limit = ref(10)
const province = ref('')
const keyword = ref('')
const industryL1 = ref('')
const busy = ref(false)
const columns = computed(() => props.tasks.find(item => item.code === task.value)?.columns ?? [])
const showProvince = computed(() => ['type', 'interpret', 'opportunity'].includes(task.value))
const showKeyword = computed(() => ['interpret', 'opportunity'].includes(task.value))

watch(open, visible => {
  if (!visible) return
  task.value = guessTask(props.tasks, props.template.fields)
  day.value = yesterday()
  province.value = ''
  keyword.value = ''
  industryL1.value = ''
})

async function confirm(): Promise<void> {
  busy.value = true
  try {
    const sample = await getTaggingSamples(task.value, day.value, limit.value, {
      province: province.value,
      keyword: keyword.value,
      industry_l1: industryL1.value,
    })
    const saved = await savePromptTestRows(props.template.id, { file_name: sample.file_name, headers: sample.headers, rows: sample.rows })
    ElMessage.success(`已取${sample.note}，测试数据已换成它`)
    open.value = false
    emit('done', saved)
  } catch (error) {
    ElMessage.error(errorMessage(error, '取测试数据失败，请重试'))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="open"
    title="从数据库取测试数据"
    width="min(560px, calc(100vw - 32px))"
  >
    <!-- novalidate：条数框按「最小值 + 步长倍数」校验会静默拦下提交，范围由后端校验。 -->
    <el-form
      label-position="top"
      novalidate
      :disabled="busy"
      @submit.prevent="confirm"
    >
      <el-form-item label="给哪个任务测">
        <el-radio-group v-model="task">
          <el-radio
            v-for="item in tasks"
            :key="item.code"
            :value="item.code"
          >
            {{ item.name }}
          </el-radio>
        </el-radio-group>
        <p class="sample__hint">
          {{ HINTS[task] }}
        </p>
      </el-form-item>
      <div class="sample__row">
        <el-form-item
          v-if="task === 'type'"
          label="采集日期"
        >
          <el-date-picker
            v-model="day"
            type="date"
            value-format="YYYY-MM-DD"
            :clearable="false"
            :disabled-date="(value: Date) => value.getTime() > Date.now()"
          />
        </el-form-item>
        <el-form-item label="条数">
          <el-input-number
            v-model="limit"
            :min="1"
            :max="50"
            controls-position="right"
          />
        </el-form-item>
        <el-form-item
          v-if="showProvince"
          label="省份（可选）"
        >
          <el-select
            v-model="province"
            filterable
            clearable
            allow-create
            default-first-option
            placeholder="搜索或选择省份"
          >
            <el-option
              v-for="name in provinces ?? []"
              :key="name"
              :label="name"
              :value="name"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          v-if="task === 'opportunity'"
          label="一级行业（可选）"
        >
          <el-select
            v-model="industryL1"
            filterable
            clearable
            allow-create
            default-first-option
            placeholder="搜索或选择一级行业"
          >
            <el-option
              v-for="name in industries ?? []"
              :key="name"
              :label="name"
              :value="name"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          v-if="showKeyword"
          label="政策名称关键词（可选）"
        >
          <el-input
            v-model="keyword"
            placeholder="留空不限"
            clearable
          />
        </el-form-item>
      </div>
      <p class="sample__note">
        列：{{ columns.map(name => `@【${name}】`).join('、') }}。正文按这个任务的设置整理（全文或截取），和正式打标一致。
        <template v-if="template.excel_name">
          会替换现在的测试数据「{{ template.excel_name }}」。
        </template>
      </p>
    </el-form>
    <template #footer>
      <el-button @click="open = false">
        取消
      </el-button>
      <el-button
        type="primary"
        :loading="busy"
        @click="confirm"
      >
        取数据
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.sample__hint { width: 100%; margin: 4px 0 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.6; }
.sample__row { display: flex; flex-wrap: wrap; gap: 0 16px; }
.sample__row :deep(.el-date-editor), .sample__row :deep(.el-input-number), .sample__row :deep(.el-input), .sample__row :deep(.el-select) { width: 180px; }
.sample__note { margin: 0; padding: 8px 12px; border-radius: 4px; background: var(--zt-soft); color: var(--zt-ink-700); font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; }
</style>
