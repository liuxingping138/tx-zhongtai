<script setup lang="ts">
import { computed } from 'vue'
import { fieldLink, fieldText, fieldValue } from './cellValue'
import { detailRows, type DetailField } from './detailSections'

/** 详情里的一组字段：左边灰底字段名、右边值，短字段两个一行，长文本占整行。 */
const props = defineProps<{ row: object; fields: readonly DetailField[] }>()
const rows = computed(() => detailRows(props.fields))
</script>

<template>
  <dl class="detail-table">
    <template
      v-for="(cells, index) in rows"
      :key="index"
    >
      <template
        v-for="field in cells"
        :key="field.column.prop"
      >
        <dt>{{ field.column.fullLabel || field.column.label }}</dt>
        <dd :class="{ 'is-span': cells.length === 1, 'is-empty': !fieldValue(row, field.column.prop) }">
          <a
            v-if="field.column.link && fieldLink(row, field.column)"
            :href="fieldLink(row, field.column)"
            target="_blank"
            rel="noopener noreferrer"
          >{{ fieldText(row, field.column) }}</a>
          <template v-else>
            {{ fieldText(row, field.column) }}
          </template>
        </dd>
      </template>
    </template>
  </dl>
</template>

<style scoped>
.detail-table { display: grid; grid-template-columns: 112px minmax(0, 1fr) 112px minmax(0, 1fr); margin: 0; border-top: 1px solid var(--zt-border); border-left: 1px solid var(--zt-border); }
.detail-table dt, .detail-table dd { margin: 0; padding: 9px 12px; border-right: 1px solid var(--zt-border); border-bottom: 1px solid var(--zt-border); line-height: 1.7; overflow-wrap: anywhere; }
.detail-table dt { background: var(--zt-soft); color: var(--zt-ink-500); font-size: 13px; }
.detail-table dd { color: var(--zt-ink-900); font-size: 14px; white-space: pre-wrap; }
.detail-table dd.is-span { grid-column: 2 / -1; }
.detail-table dd.is-empty { color: var(--zt-ink-500); }
.detail-table a { color: var(--zt-blue-600); }
@media (max-width: 767px) {
  .detail-table { grid-template-columns: 96px minmax(0, 1fr); }
  .detail-table dd.is-span { grid-column: auto; }
}
</style>
