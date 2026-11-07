<script setup lang="ts">
import { NProgress } from "naive-ui";
import { computed } from "vue";

import { fmt } from "@/lib/format";
import { station } from "@/stores/station";

const cfg = computed(() => station.state.config ?? {});
const blocksTotal = computed(() => Number(cfg.value.blocks ?? 1));
const perBlock = computed(() => Number(cfg.value.targets ?? 0));
const done = computed(() => Number(station.state.trials_done ?? 0));

const blockPercent = computed(() =>
  perBlock.value > 0 ? (100 * done.value) / perBlock.value : 0,
);
const totalPlanned = computed(() => blocksTotal.value * perBlock.value);
const totalPercent = computed(() =>
  totalPlanned.value > 0 ? (100 * station.trials.length) / totalPlanned.value : 0,
);

const elapsed = computed(() => {
  const base = station.state.block_elapsed;
  if (base === null || base === undefined) {
    return "";
  }
  const running = ["run", "feedback", "iti"].includes(String(station.state.phase));
  const extra = running ? (performance.now() - station.receivedAt) / 1000 : 0;
  const limit = Number(cfg.value.max_seconds ?? 0);
  const text = `${(base + extra).toFixed(1)} s`;
  return limit > 0 ? `${text} / ${limit} s` : text;
});
</script>

<template>
  <div class="progress">
    <div class="row">
      <span>Block {{ station.state.block ?? "–" }} / {{ blocksTotal }}</span>
      <span>Trial {{ done }} / {{ perBlock }}</span>
    </div>
    <n-progress
      type="line"
      :percentage="blockPercent"
      :show-indicator="false"
      :height="8"
      color="#0a84ff"
    />
    <div class="row">
      <span>本 block</span>
      <span>{{ elapsed }}</span>
    </div>
    <n-progress
      type="line"
      :percentage="totalPercent"
      :show-indicator="false"
      :height="8"
      color="#34c759"
    />
    <div class="row">
      <span>全部 trial</span>
      <span>{{ station.trials.length }} / {{ totalPlanned }}</span>
    </div>
    <div class="meta">
      {{ fmt(station.state.fps, 0) }} fps
      <template v-if="station.state.block_bps !== null && station.state.block_bps !== undefined">
        · 本 block BPS {{ fmt(station.state.block_bps) }}
      </template>
    </div>
  </div>
</template>

<style scoped>
.progress {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.row {
  display: flex;
  justify-content: space-between;
  color: var(--muted);
  font-size: 13px;
  margin-top: 6px;
}

.meta {
  color: var(--muted);
  font-size: 12px;
  margin-top: 8px;
}
</style>
