<script setup lang="ts">
import type { ComponentPublicInstance } from 'vue'

import type { EditorGroup } from '@/components/editorGroups'
import GroupedFields from '@/components/GroupedFields.vue'
import type { EditorFieldsHandle, RecordEditorView } from '@/composables/useRecordEditor'

const props = withDefaults(defineProps<{ editor: RecordEditorView; groups: EditorGroup[]; size?: string }>(), {
  size: '700px',
})
// 编辑器在页面里只创建一次，拆成顶层 ref 后模板能直接解包。
const { visible, saving, saveError, title, form, fields, guard, save } = props.editor
// 把表单的校验能力交给编辑器，保存前由它调用。
function bindFields(instance: Element | ComponentPublicInstance | null) {
  fields.value = (instance ?? undefined) as EditorFieldsHandle | undefined
}
</script>

<template>
  <el-drawer
    v-model="visible"
    class="editor-overlay"
    destroy-on-close
    :before-close="guard.beforeClose"
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    :title="title"
    :size="size"
  >
    <el-form
      novalidate
      :disabled="saving"
      label-position="top"
      @submit.prevent="save"
    >
      <GroupedFields
        :ref="bindFields"
        :model-value="form"
        :groups="groups"
        :submit-error="saveError"
      />
    </el-form>
    <template #footer>
      <span
        v-if="guard.dirty.value"
        class="editor-dirty"
        role="status"
      >有未保存的修改</span>
      <el-button
        :disabled="saving"
        @click="guard.close"
      >
        取消
      </el-button>
      <el-button
        type="primary"
        :loading="saving"
        @click="save"
      >
        保存
      </el-button>
    </template>
  </el-drawer>
</template>
