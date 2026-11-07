<script setup lang="ts">
import { NAlert, NButton, NCard, NConfigProvider, NDescriptions, NDescriptionsItem, NTag, zhCN, dateZhCN } from "naive-ui";
import { onMounted, ref } from "vue";

import { fetchConfig, fetchState, type Snapshot } from "@/api";

const snapshot = ref<Snapshot | null>(null);
const fields = ref<number>(0);
const error = ref<string>("");
const loading = ref<boolean>(false);

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    snapshot.value = await fetchState();
    const config = await fetchConfig();
    const schema = config.schema;
    fields.value = Array.isArray(schema) ? schema.length : 0;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
    snapshot.value = null;
  } finally {
    loading.value = false;
  }
}

onMounted(refresh);
</script>

<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN">
    <div class="page">
      <header class="bar">
        <h1>BCI Web-Grid 控制台</h1>
        <n-tag v-if="snapshot" :type="snapshot.status === 'idle' ? 'default' : 'success'" round>
          {{ snapshot.status }}
        </n-tag>
        <span class="spacer" />
        <n-button size="small" :loading="loading" @click="refresh">刷新</n-button>
      </header>

      <n-alert v-if="error" type="error" title="无法连接控制台服务" closable>
        {{ error }}
      </n-alert>

      <n-card title="Phase 0 · 脚手架自检" :bordered="true">
        <n-descriptions v-if="snapshot" :column="2" label-placement="left">
          <n-descriptions-item label="运行状态">{{ snapshot.status }}</n-descriptions-item>
          <n-descriptions-item label="可控制">{{ snapshot.control ? "是" : "只读" }}</n-descriptions-item>
          <n-descriptions-item label="当前阶段">{{ snapshot.state.phase ?? "—" }}</n-descriptions-item>
          <n-descriptions-item label="表单字段数">{{ fields }}</n-descriptions-item>
        </n-descriptions>
        <p class="hint">
          这一页只是脚手架自检：Vue 3 + TypeScript + Vite + Naive UI 已经能构建、能被 Python
          控制台在 <code>/app/</code> 下提供，并能读到 <code>/api/state</code> 与 <code>/api/config</code>。
          后续 Phase 1 会替换成完整监控界面。
        </p>
      </n-card>
    </div>
  </n-config-provider>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 20px 24px;
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

.spacer {
  flex: 1;
}

.hint {
  color: var(--muted);
  font-size: 13px;
  margin: 12px 0 0;
}

code {
  background: var(--bg);
  border-radius: 4px;
  padding: 1px 4px;
}
</style>
