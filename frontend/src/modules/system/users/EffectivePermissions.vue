<script setup lang="ts">
import { computed } from 'vue'

import type { EffectivePermission } from '@/api/types'
import { LEVEL_TEXT } from '@/permissions/catalog'

/** 用户的实际权限：多个角色叠加后每个模块取最高一档，并写明每档来自哪个角色。 */
const props = defineProps<{
  permissions: EffectivePermission[]
  accountActive: boolean
  /** 角色草稿有改动但还没保存：提示这里展示的是已保存的权限。 */
  pendingRoleChange: boolean
  error: string
}>()

/** 按分组整理，分组内保持后端的模块顺序。 */
const grouped = computed(() => {
  const out = new Map<string, EffectivePermission[]>()
  for (const item of props.permissions) {
    const key = item.group_name || '其他'
    out.set(key, [...(out.get(key) ?? []), item])
  }
  return [...out.entries()]
})

const effectiveCount = computed(() => props.permissions.filter(item => item.level !== 'NONE').length)

function sourceText(item: EffectivePermission): string {
  return item.sources
    .map(source => `${source.role_name}（${LEVEL_TEXT[source.level]}${source.active ? '' : '，角色已停用'}）`)
    .join('、')
}
</script>

<template>
  <section class="block">
    <div class="block__head">
      <h3>实际权限</h3>
      <span class="block__hint">多个角色叠加后取最高一档，共 {{ effectiveCount }} 个模块可用</span>
    </div>
    <el-alert
      v-if="!accountActive"
      type="warning"
      :closable="false"
      show-icon
      title="账号未启用，以下权限暂不生效。"
      class="block__notice"
    />
    <el-alert
      v-if="pendingRoleChange"
      type="info"
      :closable="false"
      show-icon
      title="下面是已保存的权限，保存后按新角色生效。"
      class="block__notice"
    />
    <p
      v-if="error"
      class="muted"
      role="alert"
    >
      {{ error }}
    </p>
    <el-empty
      v-else-if="!permissions.length"
      :image-size="56"
      description="还没有任何模块权限。分配一个角色后，这里会列出能用的模块。"
    />
    <div
      v-for="[group, items] in grouped"
      v-else
      :key="group"
      class="perm-group"
    >
      <h4>{{ group }}</h4>
      <div
        v-for="item in items"
        :key="item.resource_code"
        class="perm-line"
        :class="{ 'is-off': item.level === 'NONE' }"
      >
        <span class="perm-line__name">{{ item.resource_name }}</span>
        <el-tag
          size="small"
          :type="item.level === 'FULL' ? 'success' : item.level === 'NONE' ? 'info' : 'primary'"
          effect="light"
        >
          {{ item.level === 'NONE' ? '不生效' : LEVEL_TEXT[item.level] }}
        </el-tag>
        <span class="perm-line__source">来自 {{ sourceText(item) }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.block { padding: 16px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: #fff; }
.block h3 { margin: 0 0 12px; font-size: 14px; font-weight: 650; color: var(--zt-ink-900); }
.block__head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.block__hint { font-size: 12px; color: var(--zt-ink-500); }
.block__notice { margin-bottom: 12px; }
.muted { color: var(--zt-ink-500); font-size: 13px; }
.perm-group + .perm-group { margin-top: 12px; }
.perm-group h4 { margin: 0 0 6px; font-size: 12px; font-weight: 600; color: var(--zt-ink-500); }
.perm-line {
  display: grid; grid-template-columns: minmax(96px, 150px) auto minmax(0, 1fr); align-items: center; gap: 12px;
  padding: 8px 0; border-top: 1px solid #f0f3f8;
}
.perm-line__name { font-size: 13px; color: var(--zt-ink-900); }
.perm-line.is-off .perm-line__name { color: var(--zt-ink-500); text-decoration: line-through; }
.perm-line__source { font-size: 12px; color: var(--zt-ink-500); overflow-wrap: anywhere; }
</style>
