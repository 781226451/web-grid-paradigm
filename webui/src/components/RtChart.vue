<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { station } from "@/stores/station";

const canvas = ref<HTMLCanvasElement | null>(null);
let observer: ResizeObserver | null = null;

const data = computed(() => station.trials.slice(-120));

function draw(): void {
  const element = canvas.value;
  if (element === null) {
    return;
  }
  const width = element.clientWidth || 400;
  const height = 150;
  const ratio = window.devicePixelRatio || 1;
  element.width = width * ratio;
  element.height = height * ratio;

  const ctx = element.getContext("2d");
  if (ctx === null) {
    return;
  }
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#6e6e73";
  ctx.font = "11px sans-serif";

  const rows = data.value;
  if (rows.length === 0) {
    ctx.fillText("尚无 trial", 8, 20);
    return;
  }

  const maxRt = Math.max(1, ...rows.map((trial) => trial.rt));
  const left = 34;
  const bottom = height - 18;
  const top = 8;
  const plotW = width - left - 6;
  const plotH = bottom - top;

  ctx.strokeStyle = "#e3e3e8";
  ctx.lineWidth = 1;
  for (let index = 0; index <= 4; index += 1) {
    const y = bottom - (plotH * index) / 4;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(width - 6, y);
    ctx.stroke();
    ctx.fillText(((maxRt * index) / 4).toFixed(1), 2, y + 4);
  }

  const step = plotW / rows.length;
  const barWidth = Math.max(1, Math.min(18, step * 0.7));
  rows.forEach((trial, index) => {
    const x = left + index * step + (step - barWidth) / 2;
    const barHeight = (plotH * trial.rt) / maxRt;
    ctx.fillStyle = trial.outcome === "hit" ? "#0a84ff" : "#ff3b30";
    ctx.fillRect(x, bottom - barHeight, barWidth, barHeight);
    if (index > 0 && trial.block !== rows[index - 1].block) {
      ctx.strokeStyle = "#6e6e73";
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(x - (step - barWidth) / 2, top);
      ctx.lineTo(x - (step - barWidth) / 2, bottom);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#6e6e73";
      ctx.fillText(`B${trial.block}`, x, height - 4);
    }
  });
}

onMounted(() => {
  draw();
  observer = new ResizeObserver(draw);
  if (canvas.value !== null) {
    observer.observe(canvas.value);
  }
});

onBeforeUnmount(() => {
  observer?.disconnect();
});

watch(data, draw, { deep: true });
</script>

<template>
  <canvas ref="canvas" class="chart" />
</template>

<style scoped>
.chart {
  display: block;
  width: 100%;
  height: 150px;
}
</style>
