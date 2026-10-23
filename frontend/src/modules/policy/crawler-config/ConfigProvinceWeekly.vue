<script setup lang="ts">
import { computed } from 'vue'

import type { ConfigProvince, ConfigWeek } from '@/api/crawlerConfig'
import { heatLevel } from './report'

/** 分省每周配置数：行是省份，列是近几周，数字越大底色越深；末列合计，末行全国。 */
const props = defineProps<{ rows: ConfigProvince[]; weeks: ConfigWeek[]; reportStart: string; current: boolean }>()

const max = computed(() => Math.max(0, ...props.rows.flatMap(row => row.weekly)))
const sum = (values: number[]) => values.reduce((total, value) => total + value, 0)
</script>

<template>
  <p
    v-if="!weeks.length"
    class="weekly__empty"
  >
    {{ reportStart }} 那周开始按周统计。从那周起，这里每个省每周新配置了多少栏目一目了然。
  </p>
  <div
    v-else
    class="weekly"
  >
    <table>
      <thead>
        <tr>
          <th scope="col">
            省份
          </th>
          <th
            v-for="(week, index) in weeks"
            :key="week.week_from"
            scope="col"
            :class="{ 'is-selected': index === weeks.length - 1 }"
            :title="`${week.week_from} 至 ${week.week_to}`"
          >
            {{ index === weeks.length - 1 && current ? '本周' : `${week.week_from.slice(5)} 起` }}
          </th>
          <th scope="col">
            合计
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.province_name"
        >
          <th scope="row">
            {{ row.province_name }}
          </th>
          <td
            v-for="(value, index) in row.weekly"
            :key="index"
            :style="{ '--heat': heatLevel(value, max) }"
            :class="{ 'is-zero': !value }"
          >
            {{ value || '·' }}
          </td>
          <td class="weekly__sum">
            {{ sum(row.weekly) }}
          </td>
        </tr>
      </tbody>
      <tfoot>
        <tr>
          <th scope="row">
            合计
          </th>
          <td
            v-for="week in weeks"
            :key="week.week_from"
          >
            {{ week.new }}
          </td>
          <td class="weekly__sum">
            {{ sum(weeks.map(week => week.new)) }}
          </td>
        </tr>
      </tfoot>
    </table>
  </div>
</template>

<style scoped>
.weekly { overflow-x: auto; }
.weekly table { width: 100%; border-collapse: separate; border-spacing: 3px; font-size: 13px; font-variant-numeric: tabular-nums; }
.weekly th, .weekly td { padding: 6px 8px; white-space: nowrap; }
.weekly thead th { color: var(--zt-ink-500); font-size: 12px; font-weight: 500; text-align: center; }
.weekly thead th:first-child, .weekly tbody th, .weekly tfoot th { text-align: left; color: var(--zt-ink-900); font-weight: 400; position: sticky; left: 0; background: var(--zt-panel); }
.weekly thead th.is-selected { color: var(--zt-blue-600); font-weight: 600; }
.weekly td { min-width: 56px; text-align: center; border-radius: 4px; color: var(--zt-ink-900); background: color-mix(in srgb, var(--chart-normal) calc(var(--heat, 0) * 100%), transparent); }
.weekly td.is-zero { color: var(--zt-ink-500); background: var(--zt-soft); }
.weekly .weekly__sum { font-weight: 600; background: none; }
.weekly tfoot th, .weekly tfoot td { font-weight: 600; background: var(--zt-soft); }
.weekly__empty { margin: 0; padding: 28px 16px; color: var(--zt-ink-500); font-size: 13px; text-align: center; }
</style>
