<script setup lang="ts">
import { NInput, NInputNumber, NSelect, NSwitch } from "naive-ui";
import { computed } from "vue";

import type { FieldSchema } from "@/stores/config";

const props = defineProps<{
  field: FieldSchema;
  modelValue: string | number | boolean;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  (event: "update:modelValue", value: string | number | boolean): void;
}>();

const choices = computed(() =>
  (props.field.options ?? []).map((option) => ({ label: option, value: option })),
);
</script>

<template>
  <n-switch
    v-if="field.type === 'bool'"
    :value="modelValue as boolean"
    :disabled="disabled"
    @update:value="emit('update:modelValue', $event)"
  />
  <n-select
    v-else-if="field.type === 'choice'"
    :value="modelValue as string"
    :options="choices"
    :disabled="disabled"
    @update:value="emit('update:modelValue', $event)"
  />
  <n-input-number
    v-else-if="field.type === 'int' || field.type === 'float'"
    :value="modelValue as number"
    :min="field.min"
    :max="field.max"
    :step="field.step ?? (field.type === 'int' ? 1 : 0.1)"
    :precision="field.type === 'float' ? 2 : 0"
    :disabled="disabled"
    class="number"
    @update:value="emit('update:modelValue', $event ?? 0)"
  />
  <n-input
    v-else
    :value="modelValue as string"
    :disabled="disabled"
    @update:value="emit('update:modelValue', $event)"
  />
</template>

<style scoped>
.number {
  width: 100%;
}
</style>
