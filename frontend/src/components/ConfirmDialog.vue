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

<style scoped>
.confirm-layer { position:fixed; inset:0; z-index:1000; display:grid; place-items:center; padding:22px; background:var(--prompt-snow-overlay); }
.confirm-dialog { width:min(420px,100%); padding:24px; border:1px solid var(--prompt-snow-border-strong); background:var(--prompt-snow-surface); color:var(--prompt-snow-text); box-shadow:var(--prompt-snow-shadow); }
.confirm-dialog h2 { margin:0; font-size:18px; }.confirm-dialog p { margin:10px 0 0; color:var(--prompt-snow-text-muted); line-height:1.55; }.confirm-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:22px; }.confirm-actions .danger-action { border-color:var(--prompt-snow-danger); background:var(--prompt-snow-danger); color:#fff; }
</style>
