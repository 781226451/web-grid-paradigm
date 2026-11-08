<script setup lang="ts">
import { NAlert, NButton, NCard } from "naive-ui";
import { computed, onMounted } from "vue";

import InputDevice from "@/components/InputDevice.vue";
import RewardDevice from "@/components/RewardDevice.vue";
import SchemaForm from "@/components/SchemaForm.vue";
import { clearMessages, form, isBusy, loadConfig, startRun, stopRun } from "@/stores/config";
import { station } from "@/stores/station";

const busy = computed(() => isBusy());
const canStart = computed(() => form.control && !busy.value && form.loaded);
const canStop = computed(() => form.control && busy.value && station.status !== "stopping");

onMounted(() => {
  if (!form.loaded) {
    void loadConfig();
  }
});
</script>

<template>
  <n-card title="实验参数" size="small">
    <template #header-extra>
      <span class="status">{{ busy ? "实验进行中，参数已锁定" : "修改后点“启动实验”" }}</span>
    </template>

    <n-alert
      v-if="form.error"
      type="error"
      closable
      class="msg"
      @close="clearMessages"
    >
      {{ form.error }}
    </n-alert>
    <n-alert
      v-else-if="form.message"
      type="success"
      closable
      class="msg"
      @close="clearMessages"
    >
      {{ form.message }}
    </n-alert>

    <SchemaForm>
      <template #after-输入>
        <InputDevice />
      </template>
      <template #after-奖励设备>
        <RewardDevice />
      </template>
    </SchemaForm>

    <template #footer>
      <div class="actions">
        <n-button
          type="primary"
          :disabled="!canStart"
          :loading="form.starting"
          @click="startRun"
        >
          启动实验
        </n-button>
        <n-button type="error" :disabled="!canStop" @click="stopRun">中止</n-button>
      </div>
    </template>
  </n-card>
</template>

<style scoped>
.status {
  color: var(--muted);
  font-size: 12px;
}

.msg {
  margin-bottom: 10px;
}

.actions {
  display: flex;
  gap: 10px;
}
</style>
