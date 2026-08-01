<script setup lang="ts">
import { ref, watch } from "vue";

const props = defineProps<{ open: boolean; title: string; initialName?: string; busy?: boolean }>();
const emit = defineEmits<{ submit: [name: string]; cancel: [] }>();
const name = ref("");
const error = ref("");

watch(() => props.open, (open) => {
  if (open) { name.value = props.initialName ?? ""; error.value = ""; }
});

function submit() {
  const normalized = name.value.trim();
  if (!normalized) { error.value = "请输入项目名称"; return; }
  if (normalized.length > 80) { error.value = "项目名称不能超过 80 个字符"; return; }
  emit("submit", normalized);
}
</script>

<template>
  <div v-if="open" class="confirm-layer" role="dialog" aria-modal="true" @click.self="emit('cancel')">
    <form class="confirm-dialog" @submit.prevent="submit">
      <h2>{{ title }}</h2>
      <label>项目名称<input v-model="name" maxlength="80" autofocus /></label>
      <p v-if="error" class="error-message">{{ error }}</p>
      <div class="confirm-actions">
        <button type="button" class="secondary-action" :disabled="busy" @click="emit('cancel')">取消</button>
        <button type="submit" class="primary-action" :disabled="busy">确认</button>
      </div>
    </form>
  </div>
</template>
