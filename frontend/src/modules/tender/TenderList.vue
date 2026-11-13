<script setup lang="ts">
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import type { TenderKind, TenderRecord } from '@/api/tender'
import BusinessTable from '@/components/BusinessTable.vue'
import ColumnPicker from '@/components/ColumnPicker.vue'
import ExportButton from '@/components/ExportButton.vue'
import ListPage from '@/components/ListPage.vue'
import { useExcelExport } from '@/composables/useExcelExport'
import { filtersForExport, useListQuery } from '@/composables/useListQuery'
import { useAuthStore } from '@/stores/auth'
import { applyDefaultDateRange, initialQuery, tenderColumns, validateTenderSearch } from './fields'
import TenderFilters from './TenderFilters.vue'
import { useTenderList } from './useTenderList'

const props = defineProps<{ kind: TenderKind }>()
const auth = useAuthStore()
const title = computed(() => (props.kind === 'winbid' ? '中标基础数据' : '招标基础数据'))
const resource = computed(() => `tender.${props.kind}`)
const columns = tenderColumns(props.kind)
const defaults = columns.map(column => column.prop)
const selected = ref([...defaults])
const query = reactive(initialQuery())
const listQuery = useListQuery(query, (): Promise<void> => load())
const { items, total, loading, loadError, resultFiltered, hasMore, countMessage, load } = useTenderList(props.kind, listQuery)

const { exporting, onExport } = useExcelExport({
  path: `/tender/${props.kind}/export`,
  filename: `${title.value}.xlsx`,
  filters: () => filtersForExport(listQuery.applied),
})

async function changePage(page: number) {
  query.page = page
  await load()
}
async function changeSize(size: number) {
  query.page_size = size
  await changePage(1)
}

function onSearch() {
  const reason = validateTenderSearch(query)
  if (reason) {
    ElMessage.warning(reason)
    return
  }
  void listQuery.search()
}

function detailRoute(row: TenderRecord) {
  return { name: `tender-${props.kind}-detail`, params: { id: row.id }, query: { ...listQuery.requested(), project_status: row.project_status } }
}
onMounted(() => {
  if (applyDefaultDateRange(query)) {
    listQuery.captureApplied()
  }
  void load()
})
</script>

<template>
  <ListPage
    :title="title"
    :total="total ?? 0"
    :page="query.page"
    :page-size="query.page_size"
    :loading="loading"
    :error="loadError"
    @retry="load"
    @update:page="query.page = $event"
    @update:page-size="query.page_size = $event"
    @change="load"
  >
    <template #total>
      <span v-if="total !== null">共 <strong>{{ total.toLocaleString('zh-CN') }}</strong> 条记录</span>
      <span v-else>{{ countMessage }}</span>
    </template>
    <template #pagination>
      <span>第 {{ query.page }} 页 · 本页 {{ items.length }} 条</span>
      <div class="tender-pager">
        <el-select
          :model-value="query.page_size"
          aria-label="每页条数"
          style="width: 120px"
          @update:model-value="changeSize"
        >
          <el-option
            v-for="size in [10, 20, 50, 100]"
            :key="size"
            :value="size"
            :label="`${size} 条/页`"
          />
        </el-select>
        <el-button
          :disabled="loading || query.page <= 1"
          @click="changePage(query.page - 1)"
        >
          上一页
        </el-button>
        <el-button
          :disabled="loading || !hasMore"
          @click="changePage(query.page + 1)"
        >
          下一页
        </el-button>
      </div>
    </template>
    <template #filters>
      <TenderFilters
        :model-value="query"
        :applied="listQuery.applied"
        @search="onSearch"
        @reset="listQuery.resetFilters"
      />
    </template>
    <template #actions>
      <ExportButton
        :allowed="auth.canExport(resource)"
        :loading="exporting"
        :disabled="loading || !!loadError"
        hint="按当前已生效的筛选条件导出 Excel（单次最多 5 万条，不含正文）。"
        @click="onExport"
      />
      <el-button
        :icon="Refresh"
        :loading="loading"
        @click="load"
      >
        刷新
      </el-button>
    </template>
    <template #tools>
      <ColumnPicker
        v-model="selected"
        :columns="columns"
        :defaults="defaults"
      />
    </template>
    <BusinessTable
      :items="items"
      :columns="columns"
      :selected="selected"
      title-key="project_name"
      :can-write="false"
      :loading="loading"
      :filtered="resultFiltered"
      :detail-route="detailRoute"
      @reset="listQuery.resetFilters"
    >
      <template #cell-project_status="{ row }">
        <el-tag
          size="small"
          :type="row.project_status === '1' ? 'success' : 'info'"
          effect="light"
        >
          {{ row.project_status === '1' ? '通过' : '未通过' }}
        </el-tag>
      </template>
      <template #cell-is_supp_scene="{ row }">
        <el-tag
          size="small"
          :type="Number(row.is_supp_scene) === 1 ? 'primary' : 'info'"
          effect="plain"
        >
          {{ Number(row.is_supp_scene) === 1 ? '已补充' : '未补充' }}
        </el-tag>
      </template>
    </BusinessTable>
  </ListPage>
</template>

<style scoped>
.tender-pager { display: flex; align-items: center; gap: 12px; }
.tender-pager :deep(.el-button + .el-button) { margin-left: 0; }
</style>
