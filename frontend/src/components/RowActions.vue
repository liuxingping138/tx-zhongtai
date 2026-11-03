<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'

/** 表格行末的「查看」「编辑」：查看描边、编辑浅底主色，两个一样高。有独立详情页的跳过去，否则交给列表开抽屉。样式在 theme.css 的 .row-action，别的行末操作也用它。 */
defineProps<{ view?: RouteLocationRaw; edit?: RouteLocationRaw; canEdit: boolean }>()
const emit = defineEmits<{ view: []; edit: [] }>()
</script>

<template>
  <div class="row-actions">
    <RouterLink
      v-if="view"
      class="row-action"
      :to="view"
    >
      查看
    </RouterLink>
    <button
      v-else
      type="button"
      class="row-action"
      @click="emit('view')"
    >
      查看
    </button>
    <template v-if="canEdit">
      <RouterLink
        v-if="edit"
        class="row-action row-action--primary"
        :to="edit"
      >
        编辑
      </RouterLink>
      <button
        v-else
        type="button"
        class="row-action row-action--primary"
        @click="emit('edit')"
      >
        编辑
      </button>
    </template>
  </div>
</template>
