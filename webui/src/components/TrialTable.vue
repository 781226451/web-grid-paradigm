<script setup lang="ts">
import { NEmpty, NTable } from "naive-ui";
import { computed } from "vue";

import { fmt } from "@/lib/format";
import { station } from "@/stores/station";

const rows = computed(() => station.trials.slice(-50).reverse());
</script>

<template>
  <n-table v-if="rows.length" :single-line="false" size="small" class="table">
    <thead>
      <tr>
        <th>Block</th>
        <th>Trial</th>
        <th>格子</th>
        <th>结果</th>
        <th>RT (s)</th>
        <th>误点</th>
        <th>路径效率</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="row in rows" :key="`${row.block}-${row.trial}`">
        <td>{{ row.block }}</td>
        <td>{{ row.trial }}</td>
        <td>{{ row.cell }}</td>
        <td :class="row.outcome === 'hit' ? 'ok' : 'bad'">
          {{ row.outcome === "hit" ? "命中" : "超时" }}
        </td>
        <td>{{ fmt(row.rt, 3) }}</td>
        <td>{{ row.misclicks }}</td>
        <td>{{ fmt(row.path_efficiency) }}</td>
      </tr>
    </tbody>
  </n-table>
  <n-empty v-else description="尚无 trial" size="small" />
</template>

<style scoped>
.table {
  font-variant-numeric: tabular-nums;
}

.ok { color: var(--green); font-weight: 600; }
.bad { color: var(--red); font-weight: 600; }
</style>
