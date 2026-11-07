<script setup lang="ts">
import { onMounted, ref, watch } from "vue";

import { station } from "@/stores/station";

const box = ref<HTMLPreElement | null>(null);

function levelOf(line: string): string {
  const match = line.match(/\|\s*(\w+)\s*\|/);
  return match ? match[1].toUpperCase() : "";
}

function lineClass(line: string): string {
  const level = levelOf(line);
  if (level === "WARNING") return "warn";
  if (level === "ERROR" || level === "CRITICAL") return "error";
  if (level === "SUCCESS") return "success";
  return "";
}

function scrollToBottom(force = false): void {
  const element = box.value;
  if (element === null) {
    return;
  }
  const atBottom =
    element.scrollTop + element.clientHeight >= element.scrollHeight - 4;
  if (force || atBottom) {
    element.scrollTop = element.scrollHeight;
  }
}

onMounted(() => scrollToBottom(true));
watch(
  () => station.logs.length,
  () => scrollToBottom(),
);
</script>

<template>
  <pre ref="box" class="logs"><span
    v-for="(line, index) in station.logs"
    :key="index"
    :class="lineClass(line)"
  >{{ line }}
</span></pre>
</template>

<style scoped>
.logs {
  margin: 0;
  height: 180px;
  overflow: auto;
  padding: 8px 10px;
  border-radius: 8px;
  background: #1d1d1f;
  color: #e6e6e6;
  font: 12px/1.5 Consolas, "Cascadia Mono", monospace;
  white-space: pre-wrap;
}

.warn { color: #ffcc66; }
.error { color: #ff7b72; }
.success { color: #7ee787; }
</style>
