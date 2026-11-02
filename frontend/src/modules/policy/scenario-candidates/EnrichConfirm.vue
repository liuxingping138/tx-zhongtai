<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { confirmEnrich, listEnrichPending, type EnrichItem } from '@/api/codebook'
import { errorMessage } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'
import { levelName, pathText } from './candidates'

/**
 * 补充待确认：采纳进码表的新场景，AI 照同级场景的写法补好了描述，在这里逐个核对、改好后确认（写进码表各行业各客群的行）。
 * 左边是待确认的场景，右边是描述，确认完自动看下一个。
 */
const emit = defineEmits<{ count: [value: number] }>()
const auth = useAuthStore()
const canConfirm = computed(() => auth.canFull('codebook.scenarios'))

const items = ref<EnrichItem[]>([])
const loading = ref(false)
const loadError = ref('')
const selected = ref('')
const form = reactive({ desc_90: '', desc_130: '', desc_pest: '', level_desc: '' })
const saving = ref(false)
const current = computed(() => items.value.find(item => item.key === selected.value) ?? null)

const EMPTY = { key: '', desc_90: '', desc_130: '', desc_pest: '', level_desc: '' }
function pick(item: EnrichItem | undefined) {
  const { key, desc_90, desc_130, desc_pest, level_desc } = item ?? EMPTY
  selected.value = key
  Object.assign(form, { desc_90, desc_130, desc_pest, level_desc })
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    items.value = (await listEnrichPending()).items
    emit('count', items.value.length)
    pick(items.value.find(item => item.key === selected.value) ?? items.value[0])
  } catch (error) {
    loadError.value = errorMessage(error, '待确认的场景没有加载出来')
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function confirm() {
  const item = current.value
  if (!item || saving.value) return
  saving.value = true
  try {
    const out = await confirmEnrich({ path: item.path, ...form })
    const index = items.value.findIndex(entry => entry.key === item.key)
    items.value = items.value.filter(entry => entry.key !== item.key)
    emit('count', items.value.length)
    pick(items.value[index] ?? items.value[index - 1])
    ElMessage.success(`已确认「${item.path[item.path.length - 1]}」，码表里 ${out.rows} 行写上了描述${items.value.length ? '，打开了下一个' : ''}`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '没有确认成，请重试'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div
    v-loading="loading"
    class="enrich"
  >
    <el-alert
      v-if="loadError"
      type="error"
      :title="loadError"
      :closable="false"
      show-icon
    />
    <p
      v-else-if="!loading && !items.length"
      class="enrich__empty"
    >
      没有等确认的描述。采纳进码表的新场景，要在任务调度里跑过「新增场景补描述」，AI 写好描述后才会出现在这里。
    </p>
    <template v-else>
      <nav
        class="enrich__list"
        aria-label="待确认的场景"
      >
        <button
          v-for="item in items"
          :key="item.key"
          type="button"
          :class="['enrich__item', { 'is-active': item.key === selected }]"
          :aria-current="item.key === selected ? 'true' : undefined"
          @click="pick(item)"
        >
          <strong>{{ item.path[item.path.length - 1] }}</strong>
          <span>{{ pathText(item.path) }} · {{ levelName(item.level) }}</span>
          <span>{{ item.industries.length }} 个行业 · 码表 {{ item.rows }} 行</span>
        </button>
      </nav>
      <section
        v-if="current"
        class="enrich__detail"
        :aria-label="`核对「${current.path[current.path.length - 1]}」的描述`"
      >
        <h2>{{ pathText(current.path) }}</h2>
        <p class="enrich__muted">
          新增{{ levelName(current.level) }} · {{ current.industries.join('；') }}{{ current.source_policy ? ` · 来源政策：${current.source_policy}` : '' }}
        </p>
        <p
          v-if="!current.desc_90"
          class="enrich__warn"
        >
          AI 没写出来，请自己补上。
        </p>
        <el-form label-position="top">
          <el-form-item label="场景描述（90字）">
            <el-input
              v-model="form.desc_90"
              type="textarea"
              :rows="3"
              :disabled="!canConfirm"
            />
          </el-form-item>
          <el-form-item label="场景描述（130字）">
            <el-input
              v-model="form.desc_130"
              type="textarea"
              :rows="4"
              :disabled="!canConfirm"
            />
          </el-form-item>
          <el-form-item label="场景描述（PEST总结）">
            <el-input
              v-model="form.desc_pest"
              type="textarea"
              :rows="4"
              :disabled="!canConfirm"
            />
          </el-form-item>
          <el-form-item :label="`${levelName(current.level)}场景描述`">
            <el-input
              v-model="form.level_desc"
              type="textarea"
              :rows="3"
              :disabled="!canConfirm"
            />
          </el-form-item>
        </el-form>
        <div class="enrich__actions">
          <span class="enrich__muted">{{ canConfirm ? '确认后这个场景在码表各行业、各客群的行一起写上' : '确认要行业场景码表的管理权限' }}</span>
          <el-button
            type="primary"
            :disabled="!canConfirm || !form.desc_90.trim()"
            :loading="saving"
            @click="confirm"
          >
            确认无误，下一个
          </el-button>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.enrich {
  display: flex;
  flex-wrap: wrap;
  gap: var(--zt-space-4);
  align-items: flex-start;
  min-height: 240px;
}

.enrich__empty {
  margin: 0;
  color: var(--zt-ink-500);
}

.enrich__list {
  flex: 0 1 300px;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  overflow: hidden;
}

.enrich__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--zt-space-3) var(--zt-space-4);
  border: 0;
  border-top: 1px solid var(--zt-divider);
  background: var(--zt-panel);
  color: var(--zt-ink-500);
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.enrich__item:first-child {
  border-top: 0;
}

.enrich__item strong {
  color: var(--zt-ink-900);
  font-size: 14px;
}

.enrich__item.is-active {
  background: var(--el-color-primary-light-9);
  box-shadow: inset 3px 0 0 var(--el-color-primary);
}

.enrich__detail {
  flex: 999 1 480px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-2);
}

.enrich__detail h2 {
  margin: 0;
  font-size: 18px;
}

.enrich__muted {
  margin: 0;
  color: var(--zt-ink-500);
  font-size: 13px;
}

.enrich__warn {
  margin: 0;
  color: var(--zt-warning-text);
  font-size: 13px;
}

.enrich__actions {
  display: flex;
  gap: var(--zt-space-3);
  align-items: center;
  justify-content: flex-end;
}
</style>
