<script setup lang="ts">
import { computed } from 'vue'

import type { CandidateItem } from '@/api/scenarioCandidates'
import { placeOf } from './candidates'

/** 列表「挂在哪」：上面浅色的行业（涉及别的行业时带个数），下面加粗的上级场景。 */
const props = defineProps<{ candidate: CandidateItem }>()
const place = computed(() => placeOf(props.candidate))
</script>

<template>
  <div class="place">
    <span class="place__industry">{{ place.industry }}<span
      v-if="place.more"
      class="place__more"
    >+{{ place.more }} 个行业</span></span>
    <span class="place__name">{{ place.place }}</span>
  </div>
</template>

<style scoped>
.place {
  display: flex;
  flex-direction: column;
  line-height: 20px;
}

.place__industry {
  color: var(--zt-ink-500);
  font-size: 12px;
  line-height: 18px;
}

.place__more {
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 9px;
  background: var(--zt-soft);
  color: var(--zt-ink-700);
}

.place__name {
  color: var(--zt-ink-900);
  font-weight: 500;
}
</style>
