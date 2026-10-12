<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  getCrawlerAttention,
  type CrawlerAttention,
  type CrawlerAttentionSite,
  type CrawlerDroppedSite,
  type CrawlerSiteRef,
} from '@/api/crawlerMonitoringV2'
import { errorMessage } from '@/api/errors'
import { dropText } from './charts'
import CrawlerSiteTrend from './CrawlerSiteTrend.vue'

const emit = defineEmits<{ locate: [site: CrawlerSiteRef]; loaded: [data: CrawlerAttention] }>()

const ATTENTION_ERROR = '暂时无法获取需关注的网站，请稍后重试。'
const data = ref<CrawlerAttention | null>(null)
const loading = ref(false)
const error = ref('')
const picked = ref<CrawlerAttentionSite | null>(null)
const drawerOpen = ref(false)
let sequence = 0

const groups = computed(() => {
  const value = data.value
  if (!value) return []
  const { rules } = value
  return [
    {
      key: 'new_stale',
      title: '本周新停更',
      hint: `停更 ${rules.new_stale_from}–${rules.new_stale_to} 天，刚越过停更线，最值得马上排查`,
      empty: '本周没有新停更的网站',
      total: value.new_stale.total,
      items: value.new_stale.items.map(site => ({ site, metric: `停更 ${site.stale_days ?? '-'} 天`, detail: `最新入库 ${site.last_created_at || '-'}` })),
    },
    {
      key: 'dropped',
      title: '采集量骤降',
      hint: `近 7 天比前 ${rules.drop_base_weeks} 周周均下降 ${rules.drop_percent}% 以上（已扣除全网整体波动），还没到停更`,
      empty: '没有采集量骤降的网站',
      total: value.dropped.total,
      items: value.dropped.items.map((site: CrawlerDroppedSite) => ({
        site,
        metric: dropText(site.recent_rows, site.drop_rate),
        detail: `近 7 天 ${site.recent_rows.toLocaleString()} 条，前 ${rules.drop_base_weeks} 周周均 ${site.weekly_avg.toLocaleString()} 条`,
      })),
    },
  ]
})

function place(site: CrawlerSiteRef): string {
  return [site.province_name, site.city_name].filter(Boolean).join(' · ') || '未填地区'
}

function open(site: CrawlerAttentionSite) {
  picked.value = site
  drawerOpen.value = true
}

function locate() {
  if (!picked.value) return
  const { site_name: siteName, province_name: provinceName, city_name: cityName } = picked.value
  emit('locate', { site_name: siteName, province_name: provinceName, city_name: cityName })
  drawerOpen.value = false
}

async function load() {
  const current = ++sequence
  loading.value = true
  error.value = ''
  try {
    const result = await getCrawlerAttention()
    if (current !== sequence) return
    data.value = result
    emit('loaded', result)
  } catch (cause) {
    if (current === sequence) error.value = errorMessage(cause, ATTENTION_ERROR)
  } finally {
    if (current === sequence) loading.value = false
  }
}

onMounted(() => { void load() })
defineExpose({ load })
</script>

<template>
  <section
    v-loading="loading && !data"
    class="chart-panel"
  >
    <header class="chart-head">
      <div>
        <h3>需要关注</h3>
        <p class="chart-note">
          点击网站查看近 90 天采集曲线<template v-if="data">
            ；统计截至 {{ data.rules.date_to }}
          </template>
        </p>
      </div>
    </header>
    <div
      v-if="error"
      class="chart-error"
      role="alert"
    >
      {{ error }}
      <el-button
        link
        type="primary"
        @click="load"
      >
        重试
      </el-button>
    </div>
    <div
      v-else
      class="attention-groups"
    >
      <div
        v-for="group in groups"
        :key="group.key"
        class="attention-group"
      >
        <h4>{{ group.title }} <span class="attention-total">{{ group.total.toLocaleString() }} 个</span></h4>
        <p class="attention-hint">
          {{ group.hint }}
        </p>
        <p
          v-if="!group.items.length"
          class="attention-empty"
        >
          {{ group.empty }}
        </p>
        <ul v-else>
          <li
            v-for="{ site, metric, detail } in group.items"
            :key="`${site.site_name}|${site.province_name}|${site.city_name}`"
          >
            <button
              type="button"
              :title="`${site.site_name}（${place(site)}）\n${detail}`"
              @click="open(site)"
            >
              <span class="attention-name">{{ site.site_name }}</span>
              <span class="attention-place">{{ place(site) }}</span>
              <span class="attention-metric">{{ metric }}</span>
            </button>
          </li>
        </ul>
        <p
          v-if="group.total > group.items.length"
          class="attention-hint"
        >
          只列出数据量最大的 {{ group.items.length }} 个
        </p>
      </div>
    </div>
    <el-drawer
      v-model="drawerOpen"
      title="网站采集情况"
      size="min(560px, 92vw)"
    >
      <template v-if="picked">
        <h2 class="drawer-title">
          {{ picked.site_name }}
        </h2>
        <dl class="drawer-fields">
          <dt>地区</dt><dd>{{ place(picked) }}</dd>
          <dt>停更天数</dt><dd>{{ picked.stale_days ?? '-' }}</dd>
          <dt>最新入库时间</dt><dd>{{ picked.last_created_at || '-' }}</dd>
          <dt>数据总量</dt><dd>{{ picked.total_rows.toLocaleString() }}</dd>
        </dl>
        <CrawlerSiteTrend :site="picked" />
      </template>
      <template #footer>
        <el-button @click="drawerOpen = false">
          关闭
        </el-button>
        <el-button
          type="primary"
          @click="locate"
        >
          在下方列表中查看
        </el-button>
      </template>
    </el-drawer>
  </section>
</template>

<style scoped>
.attention-groups { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--zt-space-4); }
.attention-group h4 { margin: 0; font-size: 13px; font-weight: 600; color: var(--zt-ink-900); }
.attention-total { margin-left: 6px; font-weight: 400; color: var(--el-color-danger); font-variant-numeric: tabular-nums; }
.attention-hint, .attention-empty { margin: 4px 0 8px; font-size: 12px; color: var(--zt-ink-500); }
.attention-group ul { list-style: none; margin: 0; padding: 0; max-height: 300px; overflow-y: auto; border-top: 1px solid var(--zt-border); }
.attention-group li { border-bottom: 1px solid var(--zt-border); }
.attention-group button {
  display: grid; grid-template-columns: minmax(0, 1fr) 120px auto; gap: var(--zt-space-3); align-items: center;
  width: 100%; padding: 8px 4px; border: 0; background: none; font: inherit; font-size: 13px; text-align: left;
  color: var(--zt-ink-700); cursor: pointer;
}
.attention-group button:hover { background: var(--zt-soft); }
.attention-group button:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: -2px; }
.attention-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--zt-ink-900); }
.attention-place { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--zt-ink-500); font-size: 12px; }
.attention-metric { color: var(--el-color-danger); font-variant-numeric: tabular-nums; white-space: nowrap; }
.drawer-title { margin: 0 0 16px; font-size: 18px; line-height: 1.5; overflow-wrap: anywhere; }
.drawer-fields { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 8px 12px; margin: 0; font-size: 13px; }
.drawer-fields dt { color: var(--zt-ink-500); }
.drawer-fields dd { margin: 0; color: var(--zt-ink-900); }
@media (max-width: 1024px) {
  .attention-groups { grid-template-columns: minmax(0, 1fr); }
}
</style>
