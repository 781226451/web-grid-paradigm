<script setup lang="ts">
import { NForm, NFormItem } from "naive-ui";
import { computed } from "vue";

import SchemaField from "@/components/SchemaField.vue";
import { form, isBusy } from "@/stores/config";

const disabled = computed(() => !form.control || isBusy());

const groups = computed(() =>
  form.groups
    .map((group) => ({
      title: group,
      fields: form.schema.filter(
        (field) => field.group === group && !field.dialog,
      ),
    }))
    .filter((group) => group.fields.length > 0),
);
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

        <SchemaField
          :field="field"
          :model-value="form.values[field.name]"
          :disabled="disabled"
          @update:model-value="form.values[field.name] = $event"
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

/* On a single-column layout the card can grow with the page instead of
   scrolling inside 56vh. */
@media (max-width: 1000px) {
  .schema-form {
    max-height: none;
    overflow: visible;
  }
}
</style>
