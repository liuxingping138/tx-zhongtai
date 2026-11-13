<script setup lang="ts">
import ChartSkeleton from '@/components/ChartSkeleton.vue'
import TableSkeleton from '@/components/TableSkeleton.vue'
</script>

<template>
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
</template>
