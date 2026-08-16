<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { Bookmark, Check, ExternalLink, LoaderCircle, Search, X } from "lucide-vue-next";

export type PromptPickerEntry = {
  id: number;
  user_id: number;
  name: string;
  prompt: string;
  category: string;
  created_at: string;
  updated_at: string;
};

const props = defineProps<{
  open: boolean;
  currentPrompt: string;
}>();
const emit = defineEmits<{
  select: [entry: PromptPickerEntry];
  close: [];
  manage: [];
}>();

const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const entries = ref<PromptPickerEntry[]>([]);
const search = ref("");
const category = ref("");
const loading = ref(false);
const error = ref("");

const categories = computed(() => [...new Set(
  entries.value.map((entry) => entry.category.trim()).filter(Boolean),
)].sort((left, right) => left.localeCompare(right, "zh-CN")));
const visibleEntries = computed(() => {
  const query = search.value.trim().toLocaleLowerCase();
  return entries.value.filter((entry) => {
    const matchesSearch = !query
      || entry.name.toLocaleLowerCase().includes(query)
      || entry.prompt.toLocaleLowerCase().includes(query);
    const matchesCategory = !category.value
      || (category.value === "__empty__" ? !entry.category : entry.category === category.value);
    return matchesSearch && matchesCategory;
  });
});

function apiFetch(path: string, init: RequestInit = {}) {
  return fetch(`${API_BASE}${path}`, { ...init, credentials: "include" });
}

async function loadEntries() {
  loading.value = true;
  error.value = "";
  try {
    const response = await apiFetch("/api/prompts");
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(String(data?.error?.message ?? "提示词加载失败"));
    entries.value = Array.isArray(data) ? data : [];
  } catch (exception) {
    error.value = exception instanceof Error ? exception.message : "提示词加载失败";
  } finally {
    loading.value = false;
  }
}

function close() {
  emit("close");
}

watch(() => props.open, (open) => {
  if (open) {
    search.value = "";
    category.value = "";
    void loadEntries();
  }
});

onMounted(() => {
  if (props.open) void loadEntries();
});
</script>

<template>
  <div v-if="open" class="prompt-picker-layer" role="dialog" aria-modal="true" aria-label="选择提示词" @click.self="close">
    <section class="prompt-picker-dialog">
      <header class="prompt-picker-heading">
        <div><span><Bookmark :size="14" />个人提示词库</span><h2>选择提示词</h2></div>
        <button type="button" class="icon-action" aria-label="关闭选择提示词" title="关闭" @click="close"><X :size="19" /></button>
      </header>
      <div class="prompt-picker-toolbar">
        <label class="prompt-picker-search"><Search :size="16" /><input v-model="search" type="search" placeholder="搜索名称或提示词" /></label>
        <select v-model="category" aria-label="筛选提示词分类"><option value="">全部分类</option><option value="__empty__">未分类</option><option v-for="item in categories" :key="item" :value="item">{{ item }}</option></select>
      </div>
      <p v-if="error" class="error-message" role="alert">{{ error }}</p>
      <div v-if="loading" class="prompt-picker-empty"><LoaderCircle class="spin" :size="22" /><span>正在加载提示词...</span></div>
      <div v-else-if="!visibleEntries.length" class="prompt-picker-empty"><Bookmark :size="24" /><strong>{{ entries.length ? "没有匹配的提示词" : "还没有保存提示词" }}</strong><span>{{ entries.length ? "尝试更换搜索词或分类" : "先在工作台保存一条可复用提示词" }}</span></div>
      <div v-else class="prompt-picker-list">
        <article v-for="entry in visibleEntries" :key="entry.id" class="prompt-picker-entry">
          <div class="prompt-picker-entry-copy"><div><span class="prompt-picker-category">{{ entry.category || "未分类" }}</span><h3>{{ entry.name }}</h3></div><p>{{ entry.prompt }}</p></div>
          <button type="button" class="primary-action" @click="emit('select', entry)"><Check :size="15" />选择</button>
        </article>
      </div>
      <footer class="prompt-picker-footer"><button type="button" class="secondary-action" @click="emit('manage')"><ExternalLink :size="15" />打开提示词管理</button><span v-if="currentPrompt.trim()">选择后将替换当前提示词</span></footer>
    </section>
  </div>
</template>

<style scoped>
.prompt-picker-layer { position:fixed; inset:0; z-index:1000; display:grid; place-items:center; padding:22px; background:rgba(5,6,8,.72); }
.prompt-picker-dialog { width:min(760px,100%); max-height:min(720px,calc(100vh - 44px)); overflow:auto; padding:26px; background:#1b1d22; border:1px solid rgba(255,255,255,.18); box-shadow:0 24px 80px rgba(0,0,0,.35); }
.prompt-picker-heading { display:flex; justify-content:space-between; align-items:flex-start; padding-bottom:17px; border-bottom:1px solid rgba(255,255,255,.12); }.prompt-picker-heading span { display:flex; align-items:center; gap:7px; color:#d8a84e; font-size:12px; }.prompt-picker-heading h2 { margin:6px 0 0; font-size:24px; }
.prompt-picker-toolbar { display:flex; gap:10px; margin:18px 0; }.prompt-picker-search { display:flex; align-items:center; gap:8px; flex:1; min-height:40px; padding:0 11px; border:1px solid rgba(255,255,255,.18); }.prompt-picker-search input { flex:1; border:0; outline:0; background:transparent; color:inherit; }.prompt-picker-toolbar select { min-width:130px; border:1px solid rgba(255,255,255,.18); background:#191b1f; color:#f6f4ef; padding:9px 11px; }
.prompt-picker-list { display:grid; gap:9px; }.prompt-picker-entry { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px; border:1px solid rgba(255,255,255,.12); background:rgba(22,24,28,.84); }.prompt-picker-entry-copy { min-width:0; }.prompt-picker-entry-copy h3 { display:inline; margin:0 0 0 8px; font-size:16px; }.prompt-picker-category { color:#d8a84e; font-size:12px; }.prompt-picker-entry-copy p { margin:8px 0 0; color:#adb2b9; line-height:1.5; white-space:pre-wrap; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }.prompt-picker-entry .primary-action { flex:none; }.prompt-picker-empty { min-height:210px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:9px; color:#a8adb5; }.prompt-picker-empty strong { color:#f6f4ef; }.prompt-picker-footer { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-top:18px; padding-top:15px; border-top:1px solid rgba(255,255,255,.12); color:#8f969f; font-size:12px; }
@media (max-width:600px) { .prompt-picker-dialog { padding:20px; }.prompt-picker-toolbar { display:grid; }.prompt-picker-entry { align-items:flex-start; flex-direction:column; }.prompt-picker-entry .primary-action { width:100%; justify-content:center; }.prompt-picker-footer { align-items:flex-start; flex-direction:column; } }
</style>
