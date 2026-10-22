<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'

import type { PromptTemplate, TemplateCategory } from '@/api/ai'
import { ALL_CATEGORIES, inCategory } from './categories'

/** 提问配置、批量提问共用的模板列表：按类型切换、按标题查找。每行第二行的说明由页面用 meta 插槽给出。 */
const props = withDefaults(defineProps<{
  templates: PromptTemplate[]
  categories: TemplateCategory[]
  selectedId?: string
  loading?: boolean
  error?: string
  /** 一个模板都没有时的提示 */
  emptyText: string
}>(), { selectedId: '', loading: false, error: '' })
const emit = defineEmits<{ select: [template: PromptTemplate] }>()
/** 正在看的类型，「全部」为空串；页面拿它决定新模板的默认类型。 */
const category = defineModel<string>('category', { default: ALL_CATEGORIES })
const keyword = ref('')

const visible = computed(() => {
  const needle = keyword.value.trim()
  return props.templates.filter(item => inCategory(item.category, category.value) && (!needle || item.title.includes(needle)))
})
const emptyMessage = computed(() => {
  if (!props.categories.length) return '还没有分配可查看的模板类型，请联系管理员'
  return props.templates.length ? '没有匹配的模板' : props.emptyText
})
</script>

<template>
  <div class="picker">
    <div class="picker__search">
      <el-radio-group
        v-if="categories.length > 1"
        v-model="category"
        size="small"
        aria-label="按模板类型查看"
      >
        <el-radio-button :value="ALL_CATEGORIES">
          全部
        </el-radio-button>
        <el-radio-button
          v-for="item in categories"
          :key="item.code"
          :value="item.code"
        >
          {{ item.name }}
        </el-radio-button>
      </el-radio-group>
      <el-input
        v-model="keyword"
        :prefix-icon="Search"
        clearable
        placeholder="按标题查找"
        aria-label="按标题查找模板"
      />
    </div>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />
    <ul
      v-loading="loading"
      class="ai-template-list picker__list"
      aria-label="提示词模板"
    >
      <li v-if="!loading && !visible.length">
        <p class="ai-panel__hint picker__empty">
          {{ emptyMessage }}
        </p>
      </li>
      <li
        v-for="item in visible"
        :key="item.id"
      >
        <button
          type="button"
          :aria-current="item.id === selectedId"
          @click="emit('select', item)"
        >
          <strong>{{ item.title }}</strong>
          <span>{{ item.category_name }} · <slot
            name="meta"
            :item="item"
          /></span>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.picker { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.picker__search { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px 0; }
.picker__list { flex: 1; min-height: 0; }
.picker__empty { padding: 16px 8px; }
</style>
