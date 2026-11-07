<script setup lang="ts">
import { NButton, NFormItem, NInputNumber, NModal, NSelect } from "naive-ui";
import { computed, ref } from "vue";

import { form } from "@/stores/config";
import { connectReward, device, disconnectReward, testReward } from "@/stores/reward";

const show = ref(false);
const port = ref("");
const baud = ref(9600);
const message = ref("");
const busy = ref(false);

const mode = computed(() => String(form.values.reward ?? "serial"));
const status = computed(() => device());

const portOptions = computed(() =>
  (status.value.ports ?? []).map((item) => ({
    label: `${item.device}${item.description ? ` · ${item.description}` : ""}`,
    value: item.device,
  })),
);

const statusText = computed(() => {
  if (mode.value === "off") {
    return "奖励已关闭，不发送";
  }
  if (mode.value === "test") {
    return "test 模式：只写入 reward_out.txt，不使用串口";
  }
  const current = status.value;
  if (current.error !== null && !current.connected) {
    return `连接失败：${current.error}`;
  }
  if (!current.connected) {
    return "未连接";
  }
  return (
    `已连接 ${current.port} @ ${current.baud} baud` +
    ` · 已发送 ${current.sent} 次` +
    (current.errors ? ` · 失败 ${current.errors} 次` : "")
  );
});

const statusClass = computed(() => {
  if (mode.value !== "serial") return "";
  if (status.value.connected) return "on";
  if (status.value.error !== null) return "err";
  return "";
});

function open(): void {
  port.value = status.value.port || "";
  baud.value = status.value.baud || 9600;
  message.value = "";
  show.value = true;
}

async function connect(): Promise<void> {
  if (!port.value.trim()) {
    message.value = "请填写串口";
    return;
  }
  busy.value = true;
  const error = await connectReward(port.value.trim(), baud.value);
  busy.value = false;
  if (error) {
    message.value = error;
    return;
  }
  show.value = false;
  message.value = `已连接 ${port.value} @ ${baud.value} baud`;
}

async function disconnect(): Promise<void> {
  const error = await disconnectReward();
  message.value = error ? `断开失败：${error}` : "已断开";
}

async function selfTest(): Promise<void> {
  message.value = "发送中…";
  message.value = await testReward({
    reward: mode.value,
    reward_amount: form.values.reward_amount,
    reward_duration_ms: form.values.reward_duration_ms,
  });
}
</script>

<template>
  <div class="device">
    <div class="row">
      <span class="status" :class="statusClass" :title="statusText">{{ statusText }}</span>
      <n-button size="tiny" :disabled="mode !== 'serial'" @click="open">连接…</n-button>
      <n-button size="tiny" :disabled="!status.connected" @click="disconnect">断开</n-button>
      <n-button size="tiny" :disabled="mode === 'off'" @click="selfTest">测试一次</n-button>
    </div>
    <div class="msg">{{ message }}</div>

    <n-modal v-model:show="show" preset="dialog" title="连接奖励设备">
      <n-form-item label="串口" label-placement="left" :show-feedback="false" class="compact">
        <n-select
          v-model:value="port"
          :options="portOptions"
          tag
          filterable
          placeholder="COM3"
        />
      </n-form-item>
      <n-form-item label="波特率" label-placement="left" :show-feedback="false" class="compact">
        <n-input-number v-model:value="baud" :min="300" :max="2000000" :step="1" />
      </n-form-item>
      <p class="hint">
        {{
          (status.ports ?? []).length
            ? "检测到：" + status.ports.map((item) => item.device).join(", ")
            : "没有检测到串口，请确认 USB 已插好"
        }}
      </p>
      <p v-if="message" class="message">{{ message }}</p>
      <template #action>
        <n-button :loading="busy" type="primary" @click="connect">连接</n-button>
        <n-button @click="show = false">取消</n-button>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.device {
  margin-top: 6px;
}

.row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.status {
  flex: 1;
  min-width: 160px;
  color: var(--muted);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status.on { color: var(--green); }
.status.err { color: var(--red); }

.msg {
  color: var(--muted);
  font-size: 12px;
  min-height: 16px;
}

.compact {
  margin-bottom: 8px;
}

.hint {
  color: var(--muted);
  font-size: 12px;
  margin: 4px 0 0;
}

.message {
  color: var(--red);
  font-size: 12px;
  margin: 6px 0 0;
}
</style>
