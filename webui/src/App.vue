<script setup lang="ts">
import {
  NAlert,
  NCard,
  NConfigProvider,
  NDescriptions,
  NDescriptionsItem,
  NTag,
  dateZhCN,
  useMessage,
  zhCN,
} from "naive-ui";
import { computed, onBeforeUnmount, onMounted, watch } from "vue";

import BlockTable from "@/components/BlockTable.vue";
import ConfigPanel from "@/components/ConfigPanel.vue";
import GridCanvas from "@/components/GridCanvas.vue";
import HistoryRuns from "@/components/HistoryRuns.vue";
import LslCard from "@/components/LslCard.vue";
import KpiCards from "@/components/KpiCards.vue";
import LogPanel from "@/components/LogPanel.vue";
import ProgressCard from "@/components/ProgressCard.vue";
import RtChart from "@/components/RtChart.vue";
import TrialTable from "@/components/TrialTable.vue";
import { fmt, phaseLabel } from "@/lib/format";
import { connect, disconnect, station } from "@/stores/station";

const cfg = computed(() => station.state.config ?? {});
const phase = computed(() => phaseLabel(station.state.phase, station.status));
const message = useMessage();
let lastError = "";

watch(
  () => station.state.error,
  (error) => {
    if (!error) {
      lastError = "";
      return;
    }
    if (error === lastError) {
      return;
    }
    lastError = error;
    message.error(`实验启动/运行失败：${error}`, {
      duration: 8000,
      closable: true,
    });
  },
);

const tagType = computed(() => {
  const value = String(station.state.phase ?? "");
  if (station.status === "idle") return "default";
  if (value === "done" || value === "finished") return "info";
  if (station.state.aborted) return "error";
  return "success";
});

const where = computed(() =>
  station.state.subject
    ? `${station.state.subject} · ses-${station.state.session_id ?? ""}`
    : "",
);

const info = computed(() => {
  const config = cfg.value;
  const reward =
    config.reward === "serial"
      ? station.rewardDevice?.connected
        ? `串口 ${station.rewardDevice.port} @ ${station.rewardDevice.baud}`
        : "串口（未连接）"
      : config.reward === "test"
        ? "test（不占用串口）"
        : config.reward === "off"
          ? "关闭"
          : "–";
  return [
    ["Grid", station.state.grid ? `${station.state.grid.rows} × ${station.state.grid.cols}` : "–"],
    ["Block × Trial", `${config.blocks ?? 1} × ${config.targets ?? 0}`],
    ["输入 / 选择", `${config.input ?? "–"} / ${config.selection ?? "–"}`],
    ["Trial 间休息", `${fmt(config.iti)} s`],
    ["Block 间休息", `${fmt(config.block_rest, 1)} s`],
    ["LSL 标记", config.lsl ? String(config.lsl_stream ?? "") : "关闭"],
    ["奖励", reward],
    ["数据目录", String(station.state.data_dir ?? "–")],
    ["错误", String(station.state.error ?? "–")],
  ];
});

onMounted(connect);
onBeforeUnmount(disconnect);
</script>

<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN">
    <div class="page">
      <header class="bar">
        <h1>BCI Web-Grid 控制台</h1>
        <n-tag :type="tagType" round size="small">{{ phase }}</n-tag>
        <span class="where">{{ where }}</span>
        <span class="spacer" />
        <n-tag size="small" :type="station.connected ? 'success' : 'error'" round>
          {{ station.connected ? "已连接" : "未连接" }}
        </n-tag>
      </header>

      <n-alert v-if="station.error" type="warning" closable @close="station.error = ''">
        {{ station.error }}
      </n-alert>
      <n-alert v-if="station.state.error" type="error" class="run-error">
        实验失败：{{ station.state.error }}
      </n-alert>

      <main class="layout">
        <section class="col left">
          <ConfigPanel />
          <n-card title="实时网格" size="small">
            <GridCanvas />
          </n-card>
          <n-card title="会话信息" size="small">
            <n-descriptions :column="1" label-placement="left" size="small">
              <n-descriptions-item v-for="[label, value] in info" :key="label" :label="label">
                {{ value }}
              </n-descriptions-item>
            </n-descriptions>
          </n-card>
        </section>

        <section class="col right">
          <LslCard />
          <n-card title="进度" size="small">
            <ProgressCard />
          </n-card>
          <n-card title="本次运行表现" size="small">
            <KpiCards />
          </n-card>
          <n-card title="反应时（每个 trial；红色 = 超时）" size="small">
            <RtChart />
          </n-card>
          <n-card title="Block 结果" size="small">
            <BlockTable />
          </n-card>
          <n-card title="最近 trial" size="small">
            <TrialTable />
          </n-card>
          <n-card title="历史运行" size="small">
            <HistoryRuns />
          </n-card>
          <n-card title="日志" size="small">
            <LogPanel />
          </n-card>
        </section>
      </main>
    </div>
  </n-config-provider>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 14px 20px 24px;
}

.bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.bar h1 {
  font-size: 17px;
  margin: 0;
}

.where {
  color: var(--muted);
  font-size: 13px;
}

.spacer {
  flex: 1;
}

.layout {
  display: grid;
  grid-template-columns: minmax(300px, 380px) 1fr;
  gap: 16px;
  align-items: start;
}

@media (max-width: 1000px) {
  .layout {
    grid-template-columns: 1fr;
  }
}

.col {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}
</style>
