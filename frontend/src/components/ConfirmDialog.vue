<script setup lang="ts">
defineProps<{ open: boolean; title: string; message: string; busy?: boolean; confirmLabel?: string }>();
const emit = defineEmits<{ confirm: []; cancel: [] }>();
</script>

<template>
  <div v-if="open" class="confirm-layer" role="dialog" aria-modal="true" @click.self="emit('cancel')">
    <section class="confirm-dialog">
      <h2>{{ title }}</h2>
      <p>{{ message }}</p>
      <div class="confirm-actions">
        <button type="button" class="secondary-action" :disabled="busy" @click="emit('cancel')">取消</button>
        <button type="button" class="danger-action" :disabled="busy" @click="emit('confirm')">{{ busy ? "处理中..." : (confirmLabel ?? "确认删除") }}</button>
      </div>
    </section>
  </div>
</template>
