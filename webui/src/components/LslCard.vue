<script setup lang="ts">
import { NButton, NCard, NInput, NInputNumber } from "naive-ui";
import { computed, ref, watch } from "vue";

import { setLsl } from "@/stores/lsl";
import { station } from "@/stores/station";

const stream = ref("WebGridState");
const rate = ref(10);
const initialized = ref(false);
const edited = ref(false);
const message = ref("");
const busy = ref(false);

const status = computed(() => station.lsl ?? null);
const running = computed(() => Boolean(status.value?.enabled));

// The SSE snapshot carries the stream/rate resolved from the CLI/TOML config.
// Seed the editable fields once; later snapshots update sent/consumers and
// must not overwrite a value the experimenter is editing.
watch(
  () => station.lsl,
  (current) => {
    if (current === null || initialized.value || edited.value) {
      return;
    }
    stream.value = current.stream;
    rate.value = current.rate;
    initialized.value = true;
  },
  { immediate: true },
);

function markEdited(): void {
  edited.value = true;
}

const statusText = computed(() => {
  const current = status.value;
  if (current === null || !current.enabled) {
    return "未启用";
  }
  const base = `运行中 ${current.stream} @ ${current.rate} Hz · 已推送 ${current.sent} 条`;
  return current.consumers > 0 ? `${base} · ${current.consumers} 个客户端` : base;
});

async function toggle(): Promise<void> {
  busy.value = true;
  message.value = "";
  const error = await setLsl(!running.value, {
    stream: stream.value.trim() || "WebGridState",
    rate: rate.value,
  });
  busy.value = false;
  message.value = error ? `失败：${error}` : "";
}
</script>

<template>
  <n-card title="LSL 状态流（供其他 LSL 客户端读取）" size="small">
    <div class="row">
      <n-input
        v-model:value="stream"
        data-lsl="stream"
        size="small"
        placeholder="WebGridState"
        :disabled="running"
        @update:value="markEdited"
      />
      <n-input-number
        v-model:value="rate"
        data-lsl="rate"
        size="small"
        :min="0.5"
        :max="100"
        :step="1"
        :disabled="running"
        class="rate"
        @update:value="markEdited"
      />
      <n-button size="small" :loading="busy" @click="toggle">
        {{ running ? "停止" : "启动" }}
      </n-button>
    </div>
    <div class="status" :class="running ? 'on' : ''">{{ statusText }}</div>
    <div v-if="message" class="error">{{ message }}</div>
  </n-card>
</template>

<style scoped>
.row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.rate {
  width: 96px;
}

.status {
  margin-top: 8px;
  color: var(--muted);
  font-size: 12px;
}

.status.on {
  color: var(--green);
}

.error {
  margin-top: 4px;
  color: var(--red);
  font-size: 12px;
}
</style>
