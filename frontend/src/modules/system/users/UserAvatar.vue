<script setup lang="ts">
import { computed } from 'vue'

import { avatarText, avatarTone } from './userAvatar'

/** 彩色首字头像：颜色按用户 ID 固定，用户管理和在线用户里同一个人同一个颜色。 */
const props = defineProps<{ user: { id: string; display_name: string; username: string } }>()
const text = computed(() => avatarText(props.user))
const tone = computed(() => avatarTone(props.user.id))
</script>

<template>
  <span
    class="user-avatar"
    :class="`is-tone-${tone}`"
    aria-hidden="true"
  >{{ text }}</span>
</template>

<style scoped>
.user-avatar { display: inline-grid; flex: none; place-items: center; width: 28px; height: 28px; border-radius: 50%; color: var(--el-color-white); font-size: 13px; font-weight: 600; line-height: 1; }
.is-tone-1 { background: var(--zt-avatar-1); }
.is-tone-2 { background: var(--zt-avatar-2); }
.is-tone-3 { background: var(--zt-avatar-3); }
.is-tone-4 { background: var(--zt-avatar-4); }
.is-tone-5 { background: var(--zt-avatar-5); }
.is-tone-6 { background: var(--zt-avatar-6); }
.is-tone-7 { background: var(--zt-avatar-7); }
.is-tone-8 { background: var(--zt-avatar-8); }
</style>
