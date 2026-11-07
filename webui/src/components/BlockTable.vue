<script setup lang="ts">
import { NEmpty, NTable } from "naive-ui";
import { computed } from "vue";

import { fmt } from "@/lib/format";
import { station } from "@/stores/station";

const rows = computed(() =>
  station.blocks.map((block) => ({
    ...block,
    state: block.aborted ? "中止" : "完成",
  })),
);
</script>

<template>
  <n-table v-if="rows.length" :single-line="false" size="small" class="table">
    <thead>
      <tr>
        <th>Block</th>
        <th>尝试</th>
        <th>命中</th>
        <th>状态</th>
        <th>误点</th>
        <th>平均 RT</th>
        <th>BPS</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="row in rows" :key="row.block">
        <td>{{ row.block }}</td>
        <td>{{ row.attempts }}</td>
        <td>{{ row.hits }}</td>
        <td :class="row.aborted ? 'bad' : 'ok'">{{ row.state }}</td>
        <td>{{ row.misclicks }}</td>
        <td>{{ fmt(row.mean_rt_s) }}</td>
        <td>{{ fmt(row.bps) }}</td>
      </tr>
    </tbody>
  </n-table>
  <n-empty v-else description="尚无完成的 block" size="small" />
</template>

<style scoped>
.table {
  font-variant-numeric: tabular-nums;
}

.ok { color: var(--green); }
.bad { color: var(--red); }
</style>
