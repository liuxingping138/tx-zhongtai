<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { TenderKind, TenderRecord } from '@/api/tender'
import BusinessTable from '@/components/BusinessTable.vue'
import ColumnPicker from '@/components/ColumnPicker.vue'
import ListPage from '@/components/ListPage.vue'
import { useTenderList } from './useTenderList'
import { useListQuery } from '@/composables/useListQuery'
import TenderFilters from './TenderFilters.vue'
import { initialQuery, tenderColumns } from './fields'
const props = defineProps<{ kind: TenderKind }>()
const title = computed(() => props.kind === 'winbid' ? '中标基础数据' : '招标基础数据')
const columns = tenderColumns(props.kind)
const defaults = columns.map(column => column.prop)
const selected = ref([...defaults])
const query = reactive(initialQuery())
const listQuery = useListQuery(query, (): Promise<void> => load())
const { items, total, loading, loadError, resultFiltered, hasMore, countMessage, load } = useTenderList(props.kind, listQuery)
async function changePage(page: number) {
  query.page = page
  await load()
}
async function changeSize(size: number) {
  query.page_size = size
  await changePage(1)
}

function detailRoute(row: TenderRecord) {
  return { name: `tender-${props.kind}-detail`, params: { id: row.id }, query: { ...listQuery.requested(), project_status: row.project_status } }
}
onMounted(() => { void load() })
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
      <span v-if="total !== null">共 {{ total.toLocaleString('zh-CN') }} 条记录</span>
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
        @search="listQuery.search"
        @reset="listQuery.resetFilters"
      />
    </template>
    <template #actions>
      <el-button
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
        {{ row.project_status === '1' ? '人工已处理（信息化）' : '原始数据' }}
      </template>
      <template #cell-is_supp_scene="{ row }">
        {{ Number(row.is_supp_scene) === 1 ? '已补充' : '未补充' }}
      </template>
    </BusinessTable>
  </ListPage>
</template>

<style scoped>
.tender-pager { display: flex; align-items: center; gap: 12px; }
.tender-pager :deep(.el-button + .el-button) { margin-left: 0; }
</style>
