<script setup lang="ts">
import { computed } from 'vue'

import { useAuthStore } from '@/stores/auth'
import { levelSatisfies, type GrantLevel } from '@/permissions/levels'

const props = defineProps<{
  resource: string
  level?: GrantLevel
}>()

const auth = useAuthStore()
const allowed = computed(() => levelSatisfies(auth.resourceLevel(props.resource), props.level ?? 'READ'))
</script>

<template>
  <slot v-if="allowed" />
</template>
