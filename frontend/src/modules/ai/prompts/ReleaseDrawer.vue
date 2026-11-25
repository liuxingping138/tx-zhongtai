<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheckFilled, CircleCloseFilled, WarningFilled } from '@element-plus/icons-vue'

import { listPromptReleases, offlinePrompt, publishPrompt, type PromptTemplate, type TemplateRelease } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { formatState } from '../shared/aiText'
import { foldUnchanged, lineDiff } from './lineDiff'
import type { FitSummary } from './taskFit'
import { sampleState } from './templateStatus'

/**
 * 上线审核：管理员在这里看上线前检查、草稿比线上版本改了什么，再上线。
 * 业务人员也能打开看（只读），知道这次要请管理员上线什么。
 * 草稿和线上版本一样时没有要上线的东西：只看线上这一版的内容和上线记录，管理员可以下线。
 */
/** usedBy：哪些定时任务正在用这个模板；null 是说不清（没权限看任务设置、或政策服务暂时取不到） */
const props = defineProps<{
  template: PromptTemplate
  canRelease: boolean
  dirty: boolean
  fit?: FitSummary | null
  usedBy: string[] | null
  fromList?: boolean
}>()
const emit = defineEmits<{ changed: [template: PromptTemplate]; edit: [] }>()
const open = defineModel<boolean>({ required: true })
const busy = ref(false)
const history = ref<TemplateRelease[]>([])

type Level = 'ok' | 'warn' | 'error'
const ICONS = { ok: CircleCheckFilled, warn: WarningFilled, error: CircleCloseFilled }

const release = computed(() => props.template.release)
const nextNo = computed(() => (history.value[0]?.release_no ?? release.value?.release_no ?? 0) + 1)
const changes = computed(() => release.value?.unreleased_changes ?? [])
const draftCode = computed(() => props.template.code_table_name || props.template.code_name)
const upToDate = computed(() => Boolean(release.value && !changes.value.length))
/** 「这一版的内容」：第一次上线看草稿，没有改动时看线上那一版。 */
const shown = computed(() => {
  const online = upToDate.value ? release.value : null
  if (online) return { model: online.model_name, code: online.code, fields: online.fields, content: online.content }
  const template = props.template
  return { model: template.model_name, code: draftCode.value, fields: template.fields, content: template.content }
})

/** 上线影响谁：写准是哪个定时任务在用，没人用就说没人用，说不清就按两种情况都说。 */
const users = computed(() => (props.usedBy?.length ? `「${props.usedBy.join('、')}」` : ''))
const impact = computed(() => {
  if (props.usedBy === null) return '上线后，新发起的批量任务默认用这一版；如果有定时任务选了这个模板，它下一批也按这一版跑。'
  if (users.value) return `${users.value}定时任务正在用这个模板：上线后它下一批就按这一版跑，新发起的批量任务也默认用这一版。`
  const how = props.template.category === 'policy' ? '要让定时任务用它，到「系统管理 › 任务调度」里对应任务的设置中选它。' : ''
  return `目前没有定时任务用这个模板，上线后定时任务才能选它，新发起的批量任务也默认用这一版。${how}`
})

const checks = computed(() => {
  const template = props.template
  const items: { level: Level; text: string }[] = []
  items.push(props.dirty ? { level: 'error', text: '有未保存的修改，先保存再上线' } : { level: 'ok', text: '草稿已保存' })
  if (!template.content.trim()) items.push({ level: 'error', text: '提示词还是空的' })
  items.push(template.fields.length
    ? { level: 'ok', text: `输出 ${template.fields.length} 个字段` }
    : { level: 'error', text: '没设输出字段，结果解析不出任何字段' })
  if (formatState(template.content, template.fields) === 'stale') {
    items.push({ level: 'warn', text: '提示词里写的返回字段和输出字段对不上，模型会按旧字段回；先在编辑页更新格式要求' })
  }
  items.push(template.model_id
    ? { level: 'ok', text: `模型：${template.model_name}` }
    : { level: 'error', text: '模板上没选定模型；定时任务和批量任务不会替你挑' })
  const sample = sampleState(template)
  if (sample.kind === 'passed') items.push({ level: 'ok', text: `样本试跑：${sample.text}` })
  else if (sample.kind === 'failed') items.push({ level: 'warn', text: `样本试跑：${sample.text}，确认可以接受再上线` })
  else if (sample.kind === 'running') items.push({ level: 'warn', text: '样本试跑还没结束' })
  else items.push({ level: 'warn', text: '当前草稿还没用测试样本整批试跑过' })
  if (props.fit) items.push({ level: props.fit.level, text: `定时任务适配：${props.fit.text}` })
  return items
})
const blocked = computed(() => upToDate.value || checks.value.some(item => item.level === 'error'))

const contentDiff = computed(() => (release.value && changes.value.includes('提示词内容')
  ? foldUnchanged(lineDiff(release.value.content, props.template.content))
  : []))
const fieldDiff = computed(() => {
  const before = release.value?.fields ?? []
  const after = props.template.fields
  return { removed: before.filter(field => !after.includes(field)), added: after.filter(field => !before.includes(field)) }
})
const metaChanges = computed(() => {
  const old = release.value
  if (!old) return []
  const rows: { label: string; before: string; after: string }[] = []
  if (old.title !== props.template.title) rows.push({ label: '标题', before: old.title, after: props.template.title })
  if (old.model_id !== props.template.model_id) rows.push({ label: '模型', before: old.model_name, after: props.template.model_name || '未选' })
  if (changes.value.includes('码表')) {
    const after = draftCode.value || '不用码表'
    // 同名重传：文件名一样、内容换了，不写明的话两边看着一模一样。
    rows.push({ label: '码表', before: old.code || '不用码表', after: after === old.code ? `${after}（重新上传，内容可能不同）` : after })
  }
  if (changes.value.includes('类型')) rows.push({ label: '类型', before: `${old.category_name}类`, after: `${props.template.category_name}类` })
  return rows
})

watch(open, async visible => {
  if (!visible) return
  history.value = []
  try {
    history.value = await listPromptReleases(props.template.id)
  } catch {
    history.value = [] // 拿不到上线记录不影响审核和上线
  }
})

async function publish(): Promise<void> {
  if (blocked.value || busy.value) return
  const number = nextNo.value
  busy.value = true
  try {
    emit('changed', await publishPrompt(props.template.id, props.template.version))
    ElMessage.success(`第 ${number} 版已上线`)
    open.value = false
  } catch (error) {
    ElMessage.error(errorMessage(error, '上线失败，请重试'))
  } finally {
    busy.value = false
  }
}

async function takeOffline(): Promise<void> {
  const tasks = users.value ? `${users.value}定时任务正在用它，下线后这个任务就跑不了，要先在任务设置里换一个模板。` : ''
  const ok = await ElMessageBox.confirm(`${tasks}下线后定时任务不能再用它，批量任务仍可选当前草稿跑；已有任务和历史版本保留，可以重新上线。`, '下线模板？', {
    type: 'warning', confirmButtonText: '下线', cancelButtonText: '取消',
  }).then(() => true, () => false)
  if (!ok) return
  busy.value = true
  try {
    emit('changed', await offlinePrompt(props.template.id))
    ElMessage.success('已下线')
    open.value = false
  } catch (error) {
    ElMessage.error(errorMessage(error, '下线失败，请重试'))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-drawer
    v-model="open"
    :title="upToDate ? `「${template.title}」线上版本` : `上线「${template.title}」`"
    size="min(760px, 100vw)"
    class="editor-overlay release"
  >
    <p class="release__intro">
      {{ upToDate
        ? `线上是第 ${release?.release_no} 版，草稿和它一样，没有要上线的改动。${users ? `${users}定时任务和` : ''}批量任务默认都按这一版运行。`
        : `${impact}之后再改模板只改草稿，重新上线才生效。` }}
    </p>

    <section
      v-if="!upToDate"
      class="release__section"
    >
      <h3>上线前检查</h3>
      <ul class="release__checks">
        <li
          v-for="item in checks"
          :key="item.text"
          :class="`is-${item.level}`"
        >
          <el-icon><component :is="ICONS[item.level]" /></el-icon>{{ item.text }}
        </li>
      </ul>
    </section>

    <section class="release__section">
      <h3>{{ upToDate ? `线上第 ${release?.release_no} 版的内容` : release ? `草稿和线上第 ${release.release_no} 版相比` : '这一版的内容' }}</h3>
      <template v-if="release && !upToDate">
        <dl
          v-if="metaChanges.length"
          class="release__meta"
        >
          <template
            v-for="row in metaChanges"
            :key="row.label"
          >
            <dt>{{ row.label }}</dt>
            <dd><del>{{ row.before }}</del><span aria-hidden="true">→</span><ins>{{ row.after }}</ins></dd>
          </template>
        </dl>
        <div
          v-if="fieldDiff.removed.length || fieldDiff.added.length"
          class="release__fields"
        >
          <span class="release__label">输出字段</span>
          <del
            v-for="field in fieldDiff.removed"
            :key="`-${field}`"
          >{{ field }}</del>
          <ins
            v-for="field in fieldDiff.added"
            :key="`+${field}`"
          >{{ field }}</ins>
        </div>
        <div
          v-if="contentDiff.length"
          class="release__diff"
          aria-label="提示词改动"
        >
          <template
            v-for="(block, index) in contentDiff"
            :key="index"
          >
            <p
              v-if="block.kind === 'fold'"
              class="release__fold"
            >
              … 未改动 {{ block.count }} 行
            </p>
            <p
              v-else
              :class="`is-${block.kind}`"
            >
              <span aria-hidden="true">{{ block.kind === 'add' ? '+' : block.kind === 'del' ? '−' : ' ' }}</span>{{ block.text || ' ' }}
            </p>
          </template>
        </div>
      </template>
      <template v-else>
        <dl class="release__meta">
          <dt>模型</dt><dd>{{ shown.model || '未选' }}</dd>
          <dt>码表</dt><dd>{{ shown.code || '不用码表' }}</dd>
          <dt>输出字段</dt><dd>{{ shown.fields.join('、') || '未设置' }}</dd>
        </dl>
        <details class="release__content">
          <summary>提示词全文</summary>
          <pre>{{ shown.content }}</pre>
        </details>
      </template>
    </section>

    <section
      v-if="history.length"
      class="release__section"
    >
      <h3>上线记录</h3>
      <ol class="release__history">
        <li
          v-for="item in history"
          :key="item.id"
        >
          <strong>第 {{ item.release_no }} 版</strong>
          <span>{{ item.released_by_name }} · {{ item.released_at }}</span>
          <el-tag
            v-if="item.current"
            size="small"
            type="success"
          >
            线上
          </el-tag>
        </li>
      </ol>
    </section>

    <template #footer>
      <div class="release__footer">
        <template v-if="canRelease">
          <el-button
            v-if="release"
            text
            type="danger"
            :disabled="busy"
            @click="takeOffline"
          >
            下线
          </el-button>
          <el-button
            v-if="fromList"
            text
            type="primary"
            @click="emit('edit')"
          >
            进入编辑工作台 →
          </el-button>
          <span class="release__spacer" />
          <el-button @click="open = false">
            {{ upToDate ? '关闭' : '取消' }}
          </el-button>
          <el-button
            v-if="!upToDate"
            type="primary"
            :loading="busy"
            :disabled="blocked"
            @click="publish"
          >
            上线第 {{ nextNo }} 版
          </el-button>
        </template>
        <template v-else>
          <p class="release__muted">
            {{ upToDate ? '没有要上线的改动。' : `上线由管理员操作。确认无误后请管理员上线第 ${nextNo} 版。` }}
          </p>
          <el-button @click="open = false">
            关闭
          </el-button>
        </template>
      </div>
    </template>
  </el-drawer>
</template>

<style scoped>
.release__intro { margin: 0 0 8px; color: var(--zt-ink-500); font-size: 13px; line-height: 1.7; }
.release__section { padding: 16px 0; border-bottom: 1px solid var(--zt-border); }
.release__section:last-child { border-bottom: 0; }
.release__section h3 { margin: 0 0 12px; color: var(--zt-ink-900); font-size: 14px; font-weight: 650; }
.release__checks { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; font-size: 13px; }
.release__checks li { display: flex; align-items: flex-start; gap: 8px; line-height: 1.6; }
.release__checks .el-icon { flex: none; margin-top: 3px; font-size: 15px; }
.release__checks .is-ok .el-icon { color: var(--zt-success); }
.release__checks .is-warn .el-icon { color: var(--zt-warning); }
.release__checks .is-error { color: var(--zt-danger-text); }
.release__muted { margin: 0; color: var(--zt-ink-500); font-size: 13px; }
.release__meta { display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 8px 12px; margin: 0 0 12px; font-size: 13px; }
.release__meta dt { color: var(--zt-ink-500); }
.release__meta dd { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; overflow-wrap: anywhere; }
del { color: var(--zt-danger-text); text-decoration: line-through; }
ins { color: var(--zt-success-text); text-decoration: none; }
.release__fields { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 12px; font-size: 13px; }
.release__fields del, .release__fields ins { padding: 1px 8px; border-radius: 4px; }
.release__fields del { background: var(--zt-danger-soft); }
.release__fields ins { background: var(--zt-success-soft); }
.release__label { margin-right: 6px; color: var(--zt-ink-500); }
.release__diff { max-height: 360px; overflow: auto; border: 1px solid var(--zt-border); border-radius: 6px; font-size: 13px; line-height: 1.7; }
.release__diff p { margin: 0; padding: 0 12px 0 8px; white-space: pre-wrap; overflow-wrap: anywhere; }
.release__diff span { display: inline-block; width: 16px; color: var(--zt-ink-500); }
.release__diff .is-add { background: var(--zt-success-soft); }
.release__diff .is-del { background: var(--zt-danger-soft); color: var(--zt-danger-text); }
.release__diff .release__fold { padding: 2px 12px; background: var(--zt-soft); color: var(--zt-ink-500); font-size: 12px; }
.release__content summary { color: var(--zt-blue-600); font-size: 13px; cursor: pointer; }
.release__content pre { max-height: 320px; overflow: auto; margin: 8px 0 0; padding: 12px; border-radius: 6px; background: var(--zt-soft); font: inherit; font-size: 13px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.release__history { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; font-size: 13px; }
.release__history li { display: flex; align-items: center; gap: 12px; }
.release__history span { color: var(--zt-ink-500); }
.release__footer { display: flex; align-items: center; gap: 10px; }
.release__footer .el-button { margin: 0; }
.release__spacer { flex: 1; }
.release__footer .release__muted { flex: 1; text-align: left; }
</style>
