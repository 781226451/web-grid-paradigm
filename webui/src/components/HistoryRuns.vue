<script setup lang="ts">
import { NEmpty, NTable } from "naive-ui";
import { computed } from "vue";

import { fmt } from "@/lib/format";
import { station } from "@/stores/station";

const rows = computed(() => [...station.runs].reverse());

function outcome(run: (typeof station.runs)[number]): string {
  if (run.status === "aborted") return "中止";
  if (run.status === "error") return "出错";
  return "完成";
}

function outcomeClass(run: (typeof station.runs)[number]): string {
  return run.status === "aborted" || run.status === "error" ? "bad" : "ok";
}
</script>

<template>
  <n-table v-if="rows.length" :single-line="false" size="small" class="table">
    <thead>
      <tr>
        <th>#</th>
        <th>被试</th>
        <th>Block×Trial</th>
        <th>Grid</th>
        <th>命中/尝试</th>
        <th>BPS</th>
        <th>状态</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="run in rows" :key="run.id">
        <td>{{ run.id }}</td>
        <td>{{ run.subject }}</td>
        <td>{{ run.blocks }} × {{ run.trials_per_block }}</td>
        <td>{{ run.rows }} × {{ run.cols }}</td>
        <td>{{ run.hits ?? "–" }} / {{ run.attempts ?? "–" }}</td>
        <td>{{ fmt(run.bps) }}</td>
        <td :class="outcomeClass(run)">{{ outcome(run) }}</td>
      </tr>
    </tbody>
  </n-table>
  <n-empty v-else description="尚无记录" size="small" />
</template>

<style scoped>
.table {
  font-variant-numeric: tabular-nums;
}

.ok { color: var(--green); }
.bad { color: var(--red); }
</style>
