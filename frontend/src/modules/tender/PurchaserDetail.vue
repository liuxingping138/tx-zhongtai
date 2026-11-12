<script setup lang="ts">
import { useRoute } from 'vue-router'
import TenderDetail from './TenderDetail.vue'
const route = useRoute()
</script>
<template>
  <TenderDetail
    :key="String(route.params.id) + String(route.query.project_status)"
    kind="purchaser"
  />
</template>
