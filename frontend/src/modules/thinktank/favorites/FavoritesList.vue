<script setup lang="ts">
import { RefreshRight, Search, Star } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { downloadBlob } from '@/api/download'
import { errorMessage } from '@/api/errors'
import {
  downloadThinktankItemBlob,
  listThinktankFavorites,
  unfavoriteThinktankItem,
  type ThinktankFavoriteEntry,
} from '@/api/thinktank'
import ListPage from '@/components/ListPage.vue'
import TableSkeleton from '@/components/TableSkeleton.vue'
import { useAuthStore } from '@/stores/auth'
import { parseContentDispositionFilename } from '../shared/options'
import {
  applyUnfavoriteUpdate,
  buildFavoriteTabs,
  EMPTY_FAVORITE_COUNTS,
  favoriteRowKey,
  permittedQuickLinks,
  type FavoriteCounts,
  type FavoriteTabKey,
} from './favorites'
import FavoritesTable from './FavoritesTable.vue'

const auth = useAuthStore()
const activeLibrary = ref<FavoriteTabKey>('all')
const keywordInput = ref('')
const appliedKeyword = ref('')
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const loadError = ref('')
const items = ref<ThinktankFavoriteEntry[]>([])
const total = ref(0)
const counts = ref<FavoriteCounts>({ ...EMPTY_FAVORITE_COUNTS })
const downloadingKeys = reactive(new Set<string>())
const unfavoritingKeys = reactive(new Set<string>())
let loadSeq = 0

const tabs = computed(() => buildFavoriteTabs(counts.value))
const quickLinks = computed(() => permittedQuickLinks(resource => auth.canRead(resource)))
const hasFilter = computed(() => activeLibrary.value !== 'all' || Boolean(appliedKeyword.value))

async function load() {
  const seq = ++loadSeq
  loading.value = true
  loadError.value = ''
  try {
    const res = await listThinktankFavorites({
      library: activeLibrary.value,
      keyword: appliedKeyword.value || undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    if (seq !== loadSeq) return
    items.value = res.items
    total.value = res.total
    counts.value = { ...EMPTY_FAVORITE_COUNTS, ...res.counts }
  } catch (error) {
    if (seq !== loadSeq) return
    loadError.value = errorMessage(error, '加载我的收藏失败')
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function selectLibrary(key: FavoriteTabKey) {
  if (activeLibrary.value === key) return
  activeLibrary.value = key
  page.value = 1
  void load()
}

function onSearch() {
  appliedKeyword.value = keywordInput.value.trim()
  page.value = 1
  void load()
}

function onReset() {
  activeLibrary.value = 'all'
  keywordInput.value = ''
  appliedKeyword.value = ''
  page.value = 1
  void load()
}

async function onDownload(row: ThinktankFavoriteEntry) {
  const key = favoriteRowKey(row)
  if (downloadingKeys.has(key)) return
  downloadingKeys.add(key)
  const hint = ElMessage.info({ message: `正在下载「${row.title}」，请稍候…`, duration: 0 })
  try {
    const resp = await downloadThinktankItemBlob(row.library, row.id)
    const filename = parseContentDispositionFilename(resp.headers?.['content-disposition'], row.title)
    downloadBlob(resp.data, filename)
    ElMessage.success('文件下载已开始')
  } catch (error) {
    ElMessage.error(errorMessage(error, '下载失败'))
  } finally {
    hint.close()
    downloadingKeys.delete(key)
  }
}

async function onUnfavorite(row: ThinktankFavoriteEntry) {
  const key = favoriteRowKey(row)
  if (unfavoritingKeys.has(key)) return
  unfavoritingKeys.add(key)
  try {
    await unfavoriteThinktankItem(row.library, row.id)
    const next = applyUnfavoriteUpdate(
      { items: items.value, total: total.value, counts: counts.value },
      row,
    )
    items.value = next.items
    total.value = next.total
    counts.value = next.counts
    ElMessage.success('已取消收藏')
    if (items.value.length === 0 && page.value > 1) {
      page.value -= 1
      await load()
    }
  } catch (error) {
    ElMessage.error(errorMessage(error, '取消收藏失败'))
  } finally {
    unfavoritingKeys.delete(key)
  }
}

onMounted(() => { void load() })
</script>

<template>
  <div class="favorites-page">
    <ListPage
      title="我的收藏"
      hint="聚合你在资料库、报告库与方案库中收藏的文档，按收藏时间倒序排列，便于随时查阅与下载。"
      :total="total"
      :page="page"
      :page-size="pageSize"
      :loading="loading"
      :error="loadError"
      @retry="load"
      @update:page="page = $event"
      @update:page-size="pageSize = $event"
      @change="load"
    >
      <template #filters>
        <div class="favorites-bar">
          <div
            class="lib-segments"
            role="tablist"
            aria-label="按来源库筛选"
          >
            <button
              v-for="tab in tabs"
              :key="tab.key"
              type="button"
              role="tab"
              class="lib-seg"
              :class="{ 'is-active': activeLibrary === tab.key }"
              :aria-selected="activeLibrary === tab.key"
              @click="selectLibrary(tab.key)"
            >
              <span>{{ tab.label }}</span>
              <span class="lib-seg__count">{{ tab.count }}</span>
            </button>
          </div>
          <form
            class="favorites-search"
            @submit.prevent="onSearch"
          >
            <el-input
              v-model="keywordInput"
              :prefix-icon="Search"
              clearable
              placeholder="搜索标题、类别、行业或区域…"
              aria-label="搜索收藏关键词"
              class="favorites-search__input"
              @clear="onSearch"
            />
            <el-button
              type="primary"
              native-type="submit"
              :icon="Search"
            >
              查询
            </el-button>
            <el-button
              v-if="hasFilter || keywordInput"
              :icon="RefreshRight"
              @click="onReset"
            >
              重置
            </el-button>
          </form>
        </div>
      </template>

      <TableSkeleton
        v-if="loading && items.length === 0"
        :columns="7"
        :has-actions="true"
      />

      <div
        v-else-if="items.length === 0"
        class="favorites-empty"
      >
        <span
          class="favorites-empty__icon"
          aria-hidden="true"
        >
          <el-icon :size="28"><Star /></el-icon>
        </span>
        <h2>{{ hasFilter ? '当前筛选下暂无收藏记录' : '还没有收藏任何内容' }}</h2>
        <p>
          {{ hasFilter ? '可切换其他来源库或清空搜索关键词后重试。' : '在智库浏览文档时点击星标「收藏」，文档会自动汇聚到这里。' }}
        </p>
        <div
          v-if="hasFilter"
          class="favorites-empty__links"
        >
          <el-button
            type="primary"
            plain
            @click="onReset"
          >
            查看全部收藏
          </el-button>
        </div>
        <div
          v-else-if="quickLinks.length"
          class="favorites-empty__links"
        >
          <RouterLink
            v-for="link in quickLinks"
            :key="link.library"
            :to="link.path"
            class="favorites-quick-link"
          >
            {{ link.label }}
          </RouterLink>
        </div>
      </div>

      <FavoritesTable
        v-else
        :items="items"
        :loading="loading"
        :downloading-keys="downloadingKeys"
        :unfavoriting-keys="unfavoritingKeys"
        @download="onDownload"
        @unfavorite="onUnfavorite"
      />
    </ListPage>
  </div>
</template>

<style scoped>
.favorites-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px 16px; flex-wrap: wrap; }
.lib-segments { display: inline-flex; align-items: center; gap: 4px; padding: 4px; border: 1px solid var(--zt-border); border-radius: 10px; background: var(--zt-soft); flex-wrap: wrap; }
.lib-seg { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border: 0; border-radius: 7px; background: transparent; color: var(--zt-ink-700); font: inherit; font-size: 13px; font-weight: 500; cursor: pointer; transition: background-color 0.15s ease, color 0.15s ease, box-shadow 0.15s ease; }
.lib-seg:hover { color: var(--zt-ink-900); }
.lib-seg.is-active { background: var(--zt-panel); color: var(--zt-blue-600); font-weight: 600; box-shadow: 0 1px 3px var(--zt-shadow-soft); }
.lib-seg__count { display: inline-flex; align-items: center; justify-content: center; min-width: 20px; height: 18px; padding: 0 6px; border-radius: 999px; background: var(--zt-surface-subtle); border: 1px solid var(--zt-border); color: var(--zt-ink-500); font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums; }
.lib-seg.is-active .lib-seg__count { background: var(--el-color-primary-light-9); border-color: var(--el-color-primary-light-7); color: var(--zt-blue-600); }
.favorites-search { display: flex; align-items: center; gap: 8px; flex: 1 1 320px; justify-content: flex-end; min-width: 0; }
.favorites-search__input { max-width: 340px; }
.favorites-search :deep(.el-button + .el-button) { margin-left: 0; }
.favorites-empty { min-height: 360px; padding: 40px 24px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 10px; }
.favorites-empty__icon { display: inline-flex; align-items: center; justify-content: center; width: 56px; height: 56px; border-radius: 16px; background: var(--zt-warning-soft); border: 1px solid var(--zt-warning-border); color: var(--zt-warning); }
.favorites-empty h2 { margin: 4px 0 0; font-size: 16px; font-weight: 600; color: var(--zt-ink-900); }
.favorites-empty p { margin: 0; max-width: 460px; font-size: 13px; color: var(--zt-ink-500); }
.favorites-empty__links { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin-top: 8px; }
.favorites-quick-link { display: inline-flex; align-items: center; height: 34px; padding: 0 14px; border: 1px solid var(--el-color-primary-light-7); border-radius: 8px; background: var(--el-color-primary-light-9); color: var(--zt-blue-600); font-size: 13px; font-weight: 550; text-decoration: none; transition: background-color 0.15s ease, border-color 0.15s ease; }
.favorites-quick-link:hover { background: var(--el-color-primary-light-8); border-color: var(--zt-blue-600); color: var(--zt-blue-700); }
@media (max-width: 767px) {
  .favorites-search { flex-basis: 100%; justify-content: flex-start; }
  .favorites-search__input { max-width: none; }
}
</style>
