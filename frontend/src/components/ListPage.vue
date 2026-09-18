<script setup lang="ts">
import { nextTick } from 'vue'

const PAGE_SIZES = [10, 20, 50, 100]

withDefaults(
  defineProps<{
    title: string
    hint?: string
    error?: string
    total: number
    page: number
    pageSize: number
    loading?: boolean
    hidePager?: boolean
  }>(),
  { hint: '', error: '', loading: false, hidePager: false },
)

const emit = defineEmits<{
  'update:page': [value: number]
  'update:pageSize': [value: number]
  change: []
  retry: []
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
      <div
        v-if="error"
        class="list-error"
        role="alert"
      >
        <span
          class="list-error__icon"
          aria-hidden="true"
        >!</span>
        <h2>暂时无法加载数据</h2>
        <p>{{ error }}</p>
        <el-button
          type="primary"
          :loading="loading"
          @click="$emit('retry')"
        >
          重新加载
        </el-button>
      </div>
      <slot v-else />
      <div
        v-if="!hidePager && !error"
        class="pagination-row"
      >
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
  border-radius: 10px;
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
  font-size: 20px;
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
  overflow-x: auto;
}
@media (max-width: 760px) {
  .list-page__heading {
    flex-wrap: wrap;
    padding: 16px;
  }

  .list-page__actions {
    width: 100%;
    margin-left: 0;
    justify-content: flex-start;
  }

  .filter-card {
    padding: 16px;
  }
}
.list-error { padding: 48px 20px; text-align: center; }
.list-error__icon { display: inline-grid; place-items: center; width: 38px; height: 38px; border-radius: 50%; color: #a97328; background: #fff5e6; font-size: 22px; }
.list-error h2 { margin: 14px 0 8px; color: var(--zt-ink-900); font-size: 16px; }
.list-error p { margin: 0 0 20px; color: var(--zt-ink-500); font-size: 13px; }
</style>
