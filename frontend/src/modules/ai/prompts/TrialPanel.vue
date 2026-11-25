<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeft, ArrowRight, CircleCheckFilled, Promotion, VideoPause, WarningFilled } from '@element-plus/icons-vue'

import type { AiModel, PromptTemplate } from '@/api/ai'
import { getTestRows, type TestRows } from '@/api/aiSamples'
import { compactPriceText, formatYuan, priceText } from '../shared/aiText'
import type { useAnswerStream } from '../shared/useAnswerStream'
import { usedVariables } from './promptVariables'
import SampleStrip from './SampleStrip.vue'
import { ROW_STATUS_TEXT, isProblem, trialVerdict } from './sampleView'
import type { SampleRun } from './useSampleRun'

/**
 * 试发一条：选测试样本的第几行，先看这一行要替换进提示词的数据，发出去后按输出字段列出解析结果。
 * 从样本试跑里有问题的行点过来，改完提示词再发，直接说这一行修好了没有。编辑器里 Ctrl/⌘ + Enter 同效。
 */
const props = defineProps<{
  answer: ReturnType<typeof useAnswerStream>
  model: AiModel | undefined
  canRun: boolean
  template: PromptTemplate | null
  content: string
  fields: string[]
  codeName: string
  sample: SampleRun
}>()
const emit = defineEmits<{ run: []; upload: []; sample: [] }>()
/** 测试样本第几条数据，从 0 数 */
const row = defineModel<number>('row', { required: true })

const data = ref<TestRows>({ headers: [], total: 0, rows: [] })
const loadingRows = ref(false)
const expandInput = ref(false)
/** 最近一次试发问的是哪一行：换了行就先看新一行的数据，不拿上一行的回答冒充 */
const askedRow = ref<number | null>(null)

const running = computed(() => props.answer.running.value)
const messages = computed(() => props.answer.messages.value)
const sent = computed(() => messages.value.at(-2))
const reply = computed(() => messages.value.at(-1))
const showResult = computed(() => Boolean(reply.value && askedRow.value === row.value))
const current = computed(() => data.value.rows[row.value])
const variables = computed(() => usedVariables(props.content, data.value.headers, Boolean(props.codeName)))
// 换过测试样本后第 N 行已经是另一条数据，不能拿上次试跑的结果对照。
const sampleRow = computed(() => (props.sample.state.value.same_sample === false
  ? undefined
  : props.sample.state.value.rows?.items.find(item => item.row === row.value + 1)))
const sampleNo = computed(() => props.sample.run.value?.no ?? 0)
const stripRows = computed(() => (props.sample.state.value.same_sample === false ? [] : props.sample.state.value.rows?.items ?? []))
const stripCompared = computed(() => props.sample.state.value.compare?.fixed !== undefined)
const verdict = computed(() => (showResult.value && !running.value
  ? trialVerdict(sampleRow.value, reply.value?.parsed, sampleNo.value, props.fields) : null))

function pickStripRow(number: number): void {
  if (!running.value && number >= 1 && number <= data.value.rows.length) row.value = number - 1
}
/** 下拉里用提示词引用的列来认行（项目名称、政策标题），第一列常是编号，看不出是哪一行 */
const label = (index: number) => {
  const item = data.value.rows[index]
  const values = item?.values ?? {}
  const used = variables.value.map(variable => values[variable.name]).find(Boolean)
  return `${index + 1}：${used || Object.values(values).find(Boolean) || '（空行）'}`
}

watch(() => [props.template?.id, props.template?.excel_name, props.template?.excel_rows], async () => {
  const template = props.template
  data.value = { headers: [], total: 0, rows: [] }
  if (!template?.excel_name) {
    loadingRows.value = false
    return
  }
  loadingRows.value = true
  try {
    data.value = await getTestRows(template.id)
  } catch {
    // 读不到样本时照样能试发，只是看不到这一行的数据。
  } finally {
    loadingRows.value = false
  }
  if (row.value >= data.value.rows.length) row.value = 0
}, { immediate: true })
watch(running, value => { if (value) askedRow.value = row.value })

/** 这一格太长、只给了开头时，写明整格多少字。 */
function cut(name: string): string {
  const full = current.value?.lengths[name] ?? 0
  return full > (current.value?.values[name] ?? '').length ? `共 ${full.toLocaleString()} 字，这里只列开头` : ''
}

function move(step: number): void {
  const next = row.value + step
  if (next >= 0 && next < data.value.rows.length) row.value = next
}
</script>

<template>
  <div class="trial">
    <div
      v-if="data.rows.length"
      class="trial__pick"
    >
      <el-button
        size="small"
        :icon="ArrowLeft"
        aria-label="上一行"
        title="上一行"
        :disabled="row <= 0 || running"
        @click="move(-1)"
      />
      <el-select
        v-model="row"
        size="small"
        filterable
        class="trial__rows"
        aria-label="试发哪一行"
        :disabled="running"
      >
        <el-option
          v-for="(_, index) in data.rows"
          :key="index"
          :value="index"
          :label="label(index)"
        />
      </el-select>
      <el-button
        size="small"
        :icon="ArrowRight"
        aria-label="下一行"
        title="下一行"
        :disabled="row >= data.rows.length - 1 || running"
        @click="move(1)"
      />
      <span class="trial__total">{{ data.total > data.rows.length ? `共 ${data.total} 行，这里列前 ${data.rows.length} 行` : `共 ${data.total} 行` }}</span>
    </div>
    <div
      v-if="stripRows.length"
      class="trial__strip"
    >
      <SampleStrip
        :rows="stripRows"
        :compared="stripCompared"
        :active-row="row + 1"
        @pick="pickStripRow"
      />
    </div>
    <p
      v-if="!showResult && sampleRow && isProblem(sampleRow)"
      class="trial__from"
    >
      这一行在第 {{ sampleNo }} 次样本试跑里{{ ROW_STATUS_TEXT[sampleRow.status] }}，改完提示词在这里单独试，确认修好了再整批跑。
    </p>
    <div class="trial__content">
      <template v-if="!showResult">
        <template v-if="template?.excel_name">
          <div class="trial__cap-row">
            <p class="trial__cap">
              发出去时，提示词里的变量换成这一行的数据
            </p>
            <button
              v-if="variables.length"
              type="button"
              class="trial__cap-toggle"
              @click="expandInput = !expandInput"
            >
              {{ expandInput ? '收起长文本' : '展开全文' }}
            </button>
          </div>
          <dl
            v-if="variables.length"
            class="trial__data"
            :class="{ 'is-compact': !expandInput }"
          >
            <template
              v-for="item in variables"
              :key="item.name"
            >
              <dt>{{ item.name }}</dt>
              <dd v-if="item.state === 'code'">
                {{ codeName }}<small>码表全文整份放进去</small>
              </dd>
              <dd
                v-else-if="item.state === 'column'"
                :title="current?.values[item.name]"
              >
                {{ current?.values[item.name] || '（空）' }}
                <small v-if="cut(item.name)">{{ cut(item.name) }}</small>
              </dd>
              <dd
                v-else-if="loadingRows"
              >
                正在加载样本行…
              </dd>
              <dd
                v-else
                class="is-missing"
              >
                {{ item.state === 'nocode' ? '还没选码表，这里会替换成空' : '测试样本里没有这一列，会原样发出' }}
              </dd>
            </template>
          </dl>
          <p
            v-else
            class="trial__cap"
          >
            提示词里还没有引用列，写 @ 插入变量。
          </p>
        </template>
        <p
          v-else
          class="trial__cap"
        >
          没有测试样本，变量会原样发出。
          <el-button
            link
            type="primary"
            size="small"
            @click="emit('upload')"
          >
            上传测试样本
          </el-button>
        </p>
      </template>
      <template v-else-if="reply">
        <section
          class="trial__result"
          :class="{ 'is-ok': reply.parsed, 'is-bad': reply.parsed === null || reply.error }"
          aria-label="试发结果"
        >
          <div class="trial__head">
            <template v-if="running">
              {{ reply.tip || (reply.text ? '正在回答…' : '等模型回答…') }}
            </template>
            <template v-else-if="reply.error">
              <el-icon><WarningFilled /></el-icon>{{ reply.error }}
            </template>
            <template v-else-if="reply.parsed">
              <el-icon><CircleCheckFilled /></el-icon>按输出字段解析成功{{ reply.parsed.length > 1 ? `，${reply.parsed.length} 条` : '' }}
            </template>
            <template v-else-if="reply.parsed === null">
              <el-icon><WarningFilled /></el-icon>没按输出字段返回，批量时这一行会记成「格式不对」
            </template>
            <template v-else>
              模型的回答
            </template>
            <span class="trial__stat">{{ reply.time }}，输入 {{ answer.stats.usage.input.toLocaleString() }}、输出 {{ answer.stats.usage.output.toLocaleString() }} token，{{ formatYuan(answer.cost.value.inference + answer.cost.value.search) }}</span>
          </div>
          <dl
            v-for="(entry, index) in reply.parsed ?? []"
            :key="index"
            class="trial__fields"
          >
            <template
              v-for="field in fields"
              :key="field"
            >
              <dt>{{ field }}</dt><dd>{{ entry[field] || '—' }}</dd>
            </template>
          </dl>
          <pre
            v-if="running || !reply.parsed"
            class="trial__text"
          >{{ reply.text || reply.reasoning }}</pre>
        </section>
        <p
          v-if="verdict"
          class="trial__verdict"
        >
          <span :class="`is-${verdict.tone}`">{{ verdict.label }}</span>{{ verdict.text }}
        </p>
        <details v-if="reply.parsed && reply.text">
          <summary>原始回答</summary>
          <pre>{{ reply.text }}</pre>
        </details>
        <details v-if="sent?.text">
          <summary>发出去的整段提示词<small>{{ sent.text.length.toLocaleString() }} 字</small></summary>
          <pre>{{ sent.text }}</pre>
        </details>
        <div
          v-if="!running"
          class="trial__next"
        >
          <el-button
            v-if="row < data.rows.length - 1"
            size="small"
            @click="move(1)"
          >
            试下一行
          </el-button>
          <el-button
            size="small"
            @click="emit('sample')"
          >
            整批去样本试跑
          </el-button>
        </div>
      </template>
    </div>
    <footer class="trial__run">
      <span
        class="trial__price"
        :class="{ 'is-missing': !model?.available }"
        :title="model ? `${model.name} · ${priceText(model)}` : '请先在左上方配置栏选择推理模型'"
      >
        {{ !model ? '请先在左上方配置栏选择模型' : !model.available ? `${model.name} 暂不可用` : compactPriceText(model) }}
      </span>
      <el-button
        v-if="running"
        class="trial__cta"
        :icon="VideoPause"
        @click="answer.stop"
      >
        停止
      </el-button>
      <el-button
        v-else-if="canRun"
        type="primary"
        class="trial__cta"
        :icon="Promotion"
        :disabled="!model?.available"
        @click="emit('run')"
      >
        {{ showResult ? '再试一次' : (data.rows.length || template?.excel_name) ? '试发这一行' : '试发' }} <kbd>Ctrl ↵</kbd>
      </el-button>
    </footer>
  </div>
</template>

<style scoped>
.trial { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.trial__pick { display: flex; align-items: center; gap: 8px; padding: 10px 16px; border-bottom: 1px solid var(--zt-divider); }
.trial__strip { padding: 8px 16px 10px; border-bottom: 1px solid var(--zt-divider); background: var(--zt-surface-subtle); }
.trial__pick .el-button { margin: 0; }
.trial__rows { flex: 1; min-width: 0; }
.trial__total { flex: none; color: var(--zt-ink-500); font-size: 12px; }
.trial__from { margin: 12px 16px 0; padding: 8px 12px; border-radius: 6px; background: var(--zt-warning-soft); color: var(--zt-warning-text); font-size: 12px; line-height: 1.6; }
.trial__content { display: flex; flex-direction: column; gap: 12px; flex: 1; min-height: 0; overflow-y: auto; padding: 14px 16px; }
.trial__cap { margin: 0; color: var(--zt-ink-500); font-size: 12px; }
.trial__cap-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.trial__cap-toggle {
  display: inline-flex; align-items: center; height: 23px; padding: 0 9px;
  border: 1px solid var(--el-color-primary-light-7); border-radius: 999px;
  background: var(--el-color-primary-light-9); color: var(--zt-blue-600);
  font: 550 11.5px/1 var(--zt-font); cursor: pointer; transition: all 0.14s ease;
}
.trial__cap-toggle:hover { border-color: var(--zt-blue-600); background: var(--el-color-primary-light-8); }
.trial__data, .trial__fields { display: grid; grid-template-columns: 96px minmax(0, 1fr); margin: 0; font-size: 13px; line-height: 1.65; }
.trial__data { overflow: hidden; border: 1px solid var(--zt-border); border-radius: 10px; }
.trial__data.is-compact dd { display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; }
.trial__data dt, .trial__fields dt { padding: 8px 10px; border-bottom: 1px solid var(--zt-divider); color: var(--zt-ink-500); word-break: break-all; }
.trial__data dt { background: var(--zt-surface-subtle); }
.trial__data dd, .trial__fields dd { margin: 0; padding: 8px 12px; border-bottom: 1px solid var(--zt-divider); color: var(--zt-ink-900); word-break: break-all; }
.trial__data dt:last-of-type, .trial__data dd:last-of-type, .trial__fields dt:last-of-type, .trial__fields dd:last-of-type { border-bottom: 0; }
.trial__data small { display: block; color: var(--zt-ink-500); font-size: 12px; }
.trial__data .is-missing { color: var(--zt-warning-text); }
.trial__fields dd { font-weight: 600; }
.trial__result { overflow: hidden; border: 1px solid var(--zt-border); border-radius: 10px; }
.trial__result.is-ok { border-color: var(--zt-success-border); }
.trial__result.is-bad { border-color: var(--zt-warning-border); }
.trial__head { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; padding: 9px 12px; background: var(--zt-surface-subtle); color: var(--zt-ink-700); font-size: 13px; font-weight: 600; }
.is-ok .trial__head { background: var(--zt-success-soft); color: var(--zt-success-text); }
.is-bad .trial__head { background: var(--zt-warning-soft); color: var(--zt-warning-text); }
.trial__stat { margin-left: auto; color: var(--zt-ink-500); font-size: 12px; font-weight: 400; font-variant-numeric: tabular-nums; }
.trial__text { margin: 0; padding: 10px 12px; color: var(--zt-ink-900); font: 13px/1.7 var(--zt-font); white-space: pre-wrap; word-break: break-all; }
.trial__verdict { margin: 0; color: var(--zt-ink-700); font-size: 12px; line-height: 1.7; }
.trial__verdict span { display: inline-block; margin-right: 6px; padding: 0 5px; border-radius: 3px; font-weight: 600; line-height: 18px; }
.trial__verdict .is-good { background: var(--zt-success-soft); color: var(--zt-success-text); }
.trial__verdict .is-bad { background: var(--zt-warning-soft); color: var(--zt-warning-text); }
.trial__verdict .is-chg { background: var(--el-color-primary-light-9); color: var(--zt-blue-700); }
.trial__verdict .is-same { background: var(--zt-soft); color: var(--zt-ink-700); }
details { border: 1px solid var(--zt-border); border-radius: 6px; font-size: 13px; }
summary { padding: 9px 12px; color: var(--zt-ink-900); cursor: pointer; }
summary small { margin-left: 6px; color: var(--zt-ink-500); font-size: 12px; }
details pre { max-height: 320px; margin: 0; padding: 0 12px 12px; overflow: auto; color: var(--zt-ink-700); font: 12px/1.7 var(--zt-font); white-space: pre-wrap; word-break: break-all; }
.trial__next { display: flex; flex-wrap: wrap; gap: 8px; }
.trial__next .el-button { margin: 0; }
.trial__run { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 14px; border-top: 1px solid var(--zt-border); background: var(--zt-hero-gradient); }
.trial__run :deep(.el-button.trial__cta) { min-height: 32px; height: 32px; margin: 0; padding: 0 14px; border-radius: 999px; font-size: 12.5px; }
.trial__price { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--zt-ink-500); font-size: 11.5px; font-variant-numeric: tabular-nums; }
.trial__price.is-missing { color: var(--zt-warning-text); font-weight: 500; }
.trial__run kbd { margin-left: 6px; padding: 1px 5px; border-radius: 4px; background: color-mix(in srgb, var(--el-color-white) 24%, transparent); font: 600 10.5px/15px var(--zt-font); }
</style>
