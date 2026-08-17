<script setup lang="ts">
import { ref, watch } from "vue";
import { X } from "lucide-vue-next";

export type PromptCategory = string;
export type PromptForm = { name: string; prompt: string; category: PromptCategory };

const props = defineProps<{
  open: boolean;
  title?: string;
  initial?: Partial<PromptForm> | null;
  categorySuggestions?: string[];
}>();
const emit = defineEmits<{
  submit: [form: PromptForm];
  cancel: [];
}>();

const name = ref("");
const prompt = ref("");
const category = ref<PromptCategory>("");
const error = ref("");

watch(() => [props.open, props.initial], () => {
  if (!props.open) return;
  name.value = props.initial?.name ?? "";
  prompt.value = props.initial?.prompt ?? "";
  category.value = props.initial?.category ?? "";
  error.value = "";
}, { deep: true });

function submit() {
  if (!name.value.trim() || !prompt.value.trim()) {
    error.value = "请填写名称和提示词";
    return;
  }
  emit("submit", { name: name.value.trim(), prompt: prompt.value.trim(), category: category.value.trim() });
}
</script>

<template>
  <div v-if="open" class="prompt-editor-layer" @click.self="emit('cancel')">
    <form class="prompt-editor-dialog" @submit.prevent="submit">
      <header class="prompt-editor-heading"><div><span>个人提示词库</span><h2>{{ title ?? "保存提示词" }}</h2></div><button type="button" class="icon-action" aria-label="关闭" title="关闭" @click="emit('cancel')"><X :size="19" /></button></header>
      <label>名称<input v-model="name" maxlength="80" placeholder="例如：电影感人像" /></label>
      <label>提示词<textarea v-model="prompt" rows="8" maxlength="4000" placeholder="输入可复用的提示词" /></label>
      <label>分类（可选）<input v-model="category" maxlength="40" list="prompt-category-suggestions" placeholder="例如：商品、电影感、我的模板" /><datalist id="prompt-category-suggestions"><option v-for="suggestion in categorySuggestions ?? []" :key="suggestion" :value="suggestion" /></datalist></label>
      <p v-if="error" class="error-message" role="alert">{{ error }}</p>
      <footer class="prompt-editor-actions"><button type="button" class="secondary-action" @click="emit('cancel')">取消</button><button type="submit" class="primary-action">保存</button></footer>
    </form>
  </div>
</template>

<style scoped>
.prompt-editor-layer { position:fixed; inset:0; z-index:1000; display:grid; place-items:center; padding:22px; background:var(--prompt-snow-overlay); }
.prompt-editor-dialog { width:min(600px,100%); display:grid; gap:16px; padding:28px; background:var(--prompt-snow-surface); border:1px solid var(--prompt-snow-border-strong); box-shadow:var(--prompt-snow-shadow); color:var(--prompt-snow-text); }
.prompt-editor-heading { display:flex; justify-content:space-between; align-items:flex-start; border-bottom:1px solid var(--prompt-snow-border); padding-bottom:16px; }
.prompt-editor-heading span { color:var(--prompt-snow-accent); font-size:12px; }.prompt-editor-heading h2 { margin:5px 0 0; }
.prompt-editor-dialog label { display:grid; gap:7px; color:var(--prompt-snow-text-muted); font-size:13px; }
.prompt-editor-dialog input,.prompt-editor-dialog textarea,.prompt-editor-dialog select { box-sizing:border-box; width:100%; border:1px solid var(--prompt-snow-border); background:var(--prompt-snow-surface-muted); color:var(--prompt-snow-text); padding:10px; font:inherit; }
.prompt-editor-dialog textarea { resize:vertical; line-height:1.55; }.prompt-editor-actions { display:flex; justify-content:flex-end; gap:10px; border-top:1px solid var(--prompt-snow-border); padding-top:16px; }.prompt-editor-actions .primary-action { background:var(--prompt-snow-accent); border-color:var(--prompt-snow-accent); }
</style>
