<script setup lang="ts">
import { NButton, NFormItem, NModal } from "naive-ui";
import { computed, reactive, ref } from "vue";

import SchemaField from "@/components/SchemaField.vue";
import { form, isBusy } from "@/stores/config";

const show = ref(false);
const message = ref("");
const draft = reactive<Record<string, string | number | boolean>>({});

const mode = computed(() => String(form.values.input ?? "mouse"));
const disabled = computed(() => !form.control || isBusy());

const labels: Record<string, string> = {
  mouse: "鼠标",
  demo: "演示模式",
  joystick: "串口摇杆",
  lsl: "LSL 速度流",
};

const fields = computed(() =>
  form.schema.filter((field) => field.dialog === mode.value),
);

const title = computed(() => `配置${labels[mode.value] ?? mode.value}`);

const summary = computed(() => {
  if (mode.value === "demo") {
    return `演示 autopilot · 速度 ${form.values.demo_speed ?? 2.2}`;
  }
  if (mode.value === "joystick") {
    const port = String(form.values.joystick_port ?? "").trim() || "未设置";
    return `串口 ${port} @ ${form.values.joystick_baud ?? 9600} · ${form.values.joystick_stream_mode ?? "periodic"}`;
  }
  if (mode.value === "lsl") {
    const stream = String(form.values.lsl_velocity_stream ?? "").trim() || "未设置";
    const type = String(form.values.lsl_velocity_type ?? "").trim() || "未设置";
    return `LSL ${stream} (${type}) · 解析超时 ${form.values.lsl_velocity_timeout ?? 5} s`;
  }
  return "系统鼠标 · 无需额外参数";
});

function open(): void {
  if (fields.value.length === 0) {
    return;
  }
  message.value = "";
  for (const field of fields.value) {
    draft[field.name] = form.values[field.name];
  }
  show.value = true;
}

function confirm(): void {
  if (mode.value === "joystick" && !String(draft.joystick_port ?? "").trim()) {
    message.value = "请填写串口（例如 COM4）";
    return;
  }
  if (
    mode.value === "lsl"
    && (
      !String(draft.lsl_velocity_stream ?? "").trim()
      || !String(draft.lsl_velocity_type ?? "").trim()
    )
  ) {
    message.value = "速度流名称和类型都必须填写";
    return;
  }
  for (const field of fields.value) {
    const value = draft[field.name];
    if (value !== undefined) {
      form.values[field.name] = value;
    }
  }
  show.value = false;
}

function cancel(): void {
  show.value = false;
  message.value = "";
}
</script>

<template>
  <div class="device" data-device="input">
    <div class="row">
      <span class="status" :title="summary">{{ summary }}</span>
      <n-button
        size="tiny"
        :disabled="disabled || fields.length === 0"
        @click="open"
      >
        {{ fields.length ? "配置…" : "无需配置" }}
      </n-button>
    </div>

    <n-modal
      v-model:show="show"
      preset="dialog"
      :title="title"
      style="width: 520px"
    >
      <n-form-item
        v-for="field in fields"
        :key="field.name"
        :label="field.label"
        label-placement="left"
        :show-feedback="false"
        class="compact"
      >
        <div class="control">
          <SchemaField
            v-model="draft[field.name]"
            :field="field"
            :disabled="disabled"
          />
          <span v-if="field.hint" class="hint">{{ field.hint }}</span>
        </div>
      </n-form-item>
      <p v-if="message" class="message">{{ message }}</p>
      <template #action>
        <n-button type="primary" @click="confirm">确定</n-button>
        <n-button @click="cancel">取消</n-button>
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

.compact {
  margin-bottom: 8px;
}

.control {
  width: 100%;
}

.hint {
  display: block;
  color: var(--muted);
  font-size: 11px;
  margin-top: 2px;
}

.message {
  color: var(--red);
  font-size: 12px;
  margin: 6px 0 0;
}
</style>
