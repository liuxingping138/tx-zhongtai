<script setup lang="ts">
import ExcelImportProgress from '@/components/ExcelImportProgress.vue'
import ExcelImportResult from '@/components/ExcelImportResult.vue'
</script>

<template>
  <router-view />
  <ExcelImportProgress />
  <ExcelImportResult />
</template>
