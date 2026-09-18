<script setup lang="ts">
import { nextTick } from 'vue'

const PAGE_SIZES = [10, 20, 50, 100]

withDefaults(
  defineProps<{
    title: string
    hint?: string
    total: number
    page: number
    pageSize: number
    loading?: boolean
  }>(),
  { hint: '', loading: false },
)

const emit = defineEmits<{
  'update:page': [value: number]
  'update:pageSize': [value: number]
  change: []
}>()

async function onPage(value: number) {
  emit('update:page', value)
  await nextTick()
  emit('change')
}

async function onSize(value: number) {
  emit('update:pageSize', value)
  emit('update:page', 1)
  await nextTick()
  emit('change')
}

</script>

<template>
  <div class="list-page">
    <section class="panel list-page__heading">
      <div class="list-page__title-block">
        <span class="list-page__bar" />
        <div>
          <h1 class="list-page__title">
            {{ title }}
          </h1>
          <p
            v-if="hint"
            class="list-page__hint"
          >
            {{ hint }}
          </p>
        </div>
      </div>
      <div
        v-if="$slots.actions"
        class="list-page__actions"
      >
        <slot name="actions" />
      </div>
    </section>
    <section
      v-if="$slots.filters"
      class="panel filter-card"
    >
      <slot name="filters" />
    </section>
    <section class="panel table-card">
      <slot />
      <div class="pagination-row">
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :total="total"
          :page-sizes="PAGE_SIZES"
          :disabled="loading"
          layout="total, sizes, prev, pager, next, jumper"
          @update:current-page="onPage"
          @update:page-size="onSize"
        />
      </div>
    </section>
  </div>
</template>

<style scoped>
.list-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel {
  border: 1px solid var(--zt-border);
  border-radius: 6px;
  background: var(--zt-panel);
  box-shadow: var(--zt-shadow);
}

.list-page__heading {
  display: flex;
  align-items: center;
  gap: 18px;
  min-height: 72px;
  padding: 16px 24px;
}

.list-page__title-block {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}

.list-page__bar {
  width: 4px;
  height: 22px;
  margin-top: 3px;
  border-radius: 4px;
  background: var(--zt-blue-600);
  flex: 0 0 auto;
}

.list-page__title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}

.list-page__hint {
  margin: 6px 0 0;
  color: var(--zt-ink-500);
  font-size: 13px;
  line-height: 1.5;
}

.list-page__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-left: auto;
}

.list-page__actions :deep(.el-upload) {
  display: inline-flex;
}

.filter-card {
  padding: 16px 24px;
}

.table-card {
  padding: 8px 16px 16px;
}
</style>
