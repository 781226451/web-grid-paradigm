<script setup lang="ts">
import {
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSelect,
  NSwitch,
} from "naive-ui";
import { computed } from "vue";

import { form, isBusy, type FieldSchema } from "@/stores/config";

const disabled = computed(() => !form.control || isBusy());

const groups = computed(() =>
  form.groups
    .map((group) => ({
      title: group,
      fields: form.schema.filter((field) => field.group === group),
    }))
    .filter((group) => group.fields.length > 0),
);

function choices(field: FieldSchema) {
  return (field.options ?? []).map((option) => ({ label: option, value: option }));
}
</script>

<template>
  <n-form
    v-if="form.loaded"
    class="schema-form"
    label-placement="left"
    label-width="150"
    size="small"
    :show-feedback="false"
  >
    <section v-for="group in groups" :key="group.title" class="group">
      <h3 class="group-title">{{ group.title }}</h3>
      <n-form-item
        v-for="field in group.fields"
        :key="field.name"
        :data-field="field.name"
        class="row"
      >
        <template #label>
          <span class="label">{{ field.label }}</span>
          <span v-if="field.hint" class="hint">{{ field.hint }}</span>
        </template>

        <n-switch
          v-if="field.type === 'bool'"
          v-model:value="form.values[field.name] as boolean"
          :disabled="disabled"
        />
        <n-select
          v-else-if="field.type === 'choice'"
          v-model:value="form.values[field.name] as string"
          :options="choices(field)"
          :disabled="disabled"
        />
        <n-input-number
          v-else-if="field.type === 'int' || field.type === 'float'"
          v-model:value="form.values[field.name] as number"
          :min="field.min"
          :max="field.max"
          :step="field.step ?? (field.type === 'int' ? 1 : 0.1)"
          :precision="field.type === 'float' ? 2 : 0"
          :disabled="disabled"
          class="number"
        />
        <n-input
          v-else
          v-model:value="form.values[field.name] as string"
          :disabled="disabled"
        />
      </n-form-item>
      <slot :name="`after-${group.title}`" />
    </section>
  </n-form>
</template>

<style scoped>
.schema-form {
  max-height: 56vh;
  overflow: auto;
  padding-right: 6px;
}

.group {
  margin-bottom: 6px;
}

.group-title {
  margin: 10px 0 4px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

.row {
  margin-bottom: 2px;
}

.label {
  font-size: 13px;
}

.hint {
  display: block;
  color: var(--muted);
  font-size: 11px;
}

.number {
  width: 100%;
}
</style>
