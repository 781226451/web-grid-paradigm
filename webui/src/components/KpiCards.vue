<script setup lang="ts">
import { computed } from "vue";

import { useBlockMetrics } from "@/lib/blockMetrics";
import { fmt } from "@/lib/format";
import { station } from "@/stores/station";

const { stats } = useBlockMetrics();

const hits = computed(() => station.trials.filter((trial) => trial.outcome === "hit"));
const timeouts = computed(() => station.trials.length - hits.value.length);
const misclicks = computed(() =>
  station.trials.reduce((sum, trial) => sum + (trial.misclicks ?? 0), 0),
);
const hitRate = computed(() =>
  station.trials.length === 0
    ? "–"
    : `${Math.round((100 * hits.value.length) / station.trials.length)}%`,
);
const meanRt = computed(() =>
  hits.value.length === 0
    ? "–"
    : fmt(hits.value.reduce((sum, trial) => sum + trial.rt, 0) / hits.value.length),
);

const items = computed(() => {
  const bps = stats.value.bps;
  return [
    { label: "命中", value: String(hits.value.length), color: "var(--green)" },
    { label: "超时", value: String(timeouts.value), color: "var(--red)" },
    { label: "误点", value: String(misclicks.value), color: "var(--orange)" },
    { label: "命中率", value: hitRate.value, color: "var(--text)" },
    { label: "平均 RT (s)", value: meanRt.value, color: "var(--text)" },
    {
      label: "本 block BPS",
      value: fmt(bps),
      color: "var(--blue)",
      title:
        "log2(格子数 × 点击类型数) × max(命中 − 误点, 0) ÷ 本 block 秒数" +
        "（Nuyujukian 2021, Eqn. 2；无 delete 键故用 log2 N）",
    },
    { label: "奖励次数", value: String(station.state.reward_count ?? 0), color: "var(--purple)" },
    { label: "累计奖励量", value: String(station.state.reward_total ?? 0), color: "var(--purple)" },
  ];
});
</script>

<template>
  <div class="kpis">
    <div v-for="item in items" :key="item.label" class="kpi" :data-kpi="item.label" :title="item.title">
      <div class="value" :style="{ color: item.color }">{{ item.value }}</div>
      <div class="label">{{ item.label }}</div>
    </div>
  </div>
</template>

<style scoped>
.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
  gap: 10px;
}

.kpi {
  background: var(--bg);
  border-radius: 10px;
  padding: 10px 12px;
}

.value {
  font-size: 22px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.label {
  color: var(--muted);
  font-size: 12px;
}
</style>
