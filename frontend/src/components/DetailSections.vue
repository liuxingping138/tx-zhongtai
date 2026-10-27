<script setup lang="ts">
import DetailFieldTable from './DetailFieldTable.vue'
import type { DetailSection } from './detailSections'

/**
 * 分类展示的详情：每组一个标题、一张字段表。
 * `actions` 放在组标题右侧（如「编辑」），`body` 可以把某一组换成编辑表单，不传就是字段表。
 */
defineProps<{ row: object; sections: readonly DetailSection[] }>()
</script>

<template>
  <div class="detail-sections">
    <section
      v-for="section in sections"
      :key="section.title"
      class="detail-section"
      :data-section="section.title"
      :aria-label="section.title || undefined"
    >
      <header
        v-if="section.title"
        class="detail-section__head"
      >
        <h3>{{ section.title }}</h3>
        <slot
          name="actions"
          :section="section"
        />
      </header>
      <slot
        name="body"
        :section="section"
      >
        <DetailFieldTable
          :row="row"
          :fields="section.fields"
        />
      </slot>
    </section>
  </div>
</template>

<style scoped>
.detail-sections { display: flex; flex-direction: column; gap: 20px; }
.detail-section { scroll-margin-top: 12px; }
.detail-section__head { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 28px; margin-bottom: 8px; }
.detail-section__head h3 { margin: 0; color: var(--zt-ink-900); font-size: 15px; font-weight: 600; }
</style>
