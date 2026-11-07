<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { TARGET_COLORS } from "@/lib/format";
import { serverNow, station } from "@/stores/station";

const canvas = ref<HTMLCanvasElement | null>(null);
let frame = 0;

const grid = computed(() => station.state.grid ?? null);
const target = computed(() => station.state.target ?? null);

function draw(): void {
  const element = canvas.value;
  if (element === null) {
    return;
  }
  const width = element.clientWidth;
  const height = element.clientHeight;
  const ratio = window.devicePixelRatio || 1;
  const size = Math.max(1, Math.min(width, height));
  element.width = size * ratio;
  element.height = size * ratio;

  const ctx = element.getContext("2d");
  if (ctx === null) {
    return;
  }
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, size, size);

  const info = grid.value;
  if (info === null) {
    ctx.fillStyle = "#6e6e73";
    ctx.font = "13px sans-serif";
    ctx.fillText("等待实验窗口…", 12, 24);
    return;
  }

  const pad = 4;
  const cell = (size - 2 * pad) / Math.max(info.rows, info.cols);
  const ox = pad + (size - 2 * pad - cell * info.cols) / 2;
  const oy = pad + (size - 2 * pad - cell * info.rows) / 2;

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(ox, oy, cell * info.cols, cell * info.rows);

  const active = station.state.phase === "run";
  const current = target.value;
  if (current !== null) {
    ctx.fillStyle = active ? (TARGET_COLORS[current.button] ?? "#0a84ff") : "#d9d9de";
    ctx.fillRect(ox + current.col * cell, oy + current.row * cell, cell, cell);
    const progress = station.state.dwell_progress ?? 0;
    if (active && progress > 0.01) {
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(
        ox + current.col * cell + cell * 0.14,
        oy + (current.row + 1) * cell - cell * 0.18,
        cell * 0.72 * progress,
        Math.max(2, cell * 0.06),
      );
    }
  }

  ctx.strokeStyle = "#111111";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let col = 0; col <= info.cols; col += 1) {
    ctx.moveTo(ox + col * cell, oy);
    ctx.lineTo(ox + col * cell, oy + info.rows * cell);
  }
  for (let row = 0; row <= info.rows; row += 1) {
    ctx.moveTo(ox, oy + row * cell);
    ctx.lineTo(ox + info.cols * cell, oy + row * cell);
  }
  ctx.stroke();

  const cursor = station.state.cursor;
  if (cursor !== null && cursor !== undefined) {
    const [x, y] = cursor;
    const cx = ox + ((x - info.left - info.line) / info.pitch) * cell;
    const cy = oy + ((info.top - info.line - y) / info.pitch) * cell;
    const flashUntil = station.state.flash_until ?? 0;
    const flashing = flashUntil > serverNow();
    ctx.beginPath();
    ctx.arc(cx, cy, Math.max(4, cell * 0.16), 0, Math.PI * 2);
    ctx.fillStyle = flashing ? "#ff3b30" : "#111111";
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#ffffff";
    ctx.stroke();
  }
}

function loop(): void {
  draw();
  frame = requestAnimationFrame(loop);
}

onMounted(() => {
  loop();
});

onBeforeUnmount(() => {
  cancelAnimationFrame(frame);
});

watch(grid, draw, { deep: true });
</script>

<template>
  <div class="grid-wrap">
    <canvas ref="canvas" class="grid-canvas" />
    <div class="legend">
      <span><i class="swatch target" />当前目标</span>
      <span><i class="swatch idle" />trial 间 / 反馈</span>
      <span><i class="swatch flash" />光标闪红 = 误点</span>
      <span><i class="swatch cursor" />光标</span>
    </div>
  </div>
</template>

<style scoped>
.grid-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.grid-canvas {
  width: 100%;
  aspect-ratio: 1 / 1;
  max-height: 46vh;
  border-radius: 6px;
  background: #fafafa;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: var(--muted);
  font-size: 12px;
}

.swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 4px;
  border-radius: 2px;
  vertical-align: -1px;
}

.swatch.target { background: var(--blue); }
.swatch.idle { background: #d9d9de; }
.swatch.flash { background: var(--red); }
.swatch.cursor { background: #111111; border-radius: 50%; }
</style>
