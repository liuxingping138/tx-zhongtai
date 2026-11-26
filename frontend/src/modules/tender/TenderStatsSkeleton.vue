<script setup lang="ts">
import ChartSkeleton from '@/components/ChartSkeleton.vue'
import TableSkeleton from '@/components/TableSkeleton.vue'
</script>

<template>
  <div class="tender-stats-skeleton">
    <div class="grid-row grid-row--top">
      <section class="panel">
        <ChartSkeleton
          height="260px"
          :bars="10"
        />
      </section>
      <section class="panel">
        <ChartSkeleton
          height="260px"
          :bars="3"
        />
      </section>
    </div>
    <div class="grid-row grid-row--mid">
      <section class="panel">
        <ChartSkeleton
          height="240px"
          :bars="6"
        />
      </section>
      <section class="panel">
        <TableSkeleton
          :columns="5"
          :rows="5"
          :has-actions="false"
        />
      </section>
    </div>
    <section class="panel">
      <TableSkeleton
        :columns="6"
        :rows="6"
        :has-actions="false"
      />
    </section>
  </div>
</template>

<style scoped>
.tender-stats-skeleton {
  display: grid;
  gap: var(--zt-space-4);
}
.grid-row {
  display: grid;
  gap: var(--zt-space-4);
}
.grid-row--top {
  grid-template-columns: minmax(0, 8fr) minmax(0, 4fr);
}
.grid-row--mid {
  grid-template-columns: minmax(0, 6fr) minmax(0, 6fr);
}
.panel {
  padding: var(--zt-space-4) var(--zt-space-6);
  background: var(--zt-panel);
  border: 1px solid var(--zt-border);
  border-radius: 12px;
  box-shadow: var(--zt-shadow);
  min-width: 0;
}
@media (max-width: 1280px) {
  .grid-row--top,
  .grid-row--mid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
