<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Bookmark, Edit3, LoaderCircle, Plus, Search, Sparkles, Trash2 } from "lucide-vue-next";
import ConfirmDialog from "./ConfirmDialog.vue";
import PromptEditorDialog, { type PromptForm } from "./PromptEditorDialog.vue";

export type PromptEntry = PromptForm & {
  id: number;
  user_id: number;
  created_at: string;
  updated_at: string;
};

defineProps<{ currentPrompt?: string }>();
const emit = defineEmits<{ apply: [prompt: string, name: string]; back: [] }>();
const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const entries = ref<PromptEntry[]>([]);
const search = ref("");
const category = ref("");
const loading = ref(false);
const error = ref("");
const editorOpen = ref(false);
const editing = ref<PromptEntry | null>(null);
const saving = ref(false);
const deleting = ref<PromptEntry | null>(null);
const deletingBusy = ref(false);
const categorySuggestions = computed(() => [...new Set(
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

function apiFetch(path: string, init: RequestInit = {}) { return fetch(`${API_BASE}${path}`, { ...init, credentials: "include" }); }
async function readJson(response: Response) { try { return await response.json(); } catch { return null; } }
function message(data: any, fallback: string) { return String(data?.error?.message ?? data?.detail ?? fallback); }
function openCreate() { editing.value = null; editorOpen.value = true; }
function openEdit(entry: PromptEntry) { editing.value = entry; editorOpen.value = true; }
async function loadEntries() {
  loading.value = true; error.value = "";
  try {
    const response = await apiFetch("/api/prompts");
    const data = await readJson(response);
    if (!response.ok) throw new Error(message(data, "提示词加载失败"));
    entries.value = Array.isArray(data) ? data : [];
  } catch (exception) { error.value = exception instanceof Error ? exception.message : "提示词加载失败"; }
  finally { loading.value = false; }
}
async function saveEntry(form: PromptForm) {
  saving.value = true; error.value = "";
  try {
    const response = await apiFetch(editing.value ? `/api/prompts/${editing.value.id}` : "/api/prompts", {
      method: editing.value ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    const data = await readJson(response);
    if (!response.ok) throw new Error(message(data, "提示词保存失败"));
    editorOpen.value = false; await loadEntries();
  } catch (exception) { error.value = exception instanceof Error ? exception.message : "提示词保存失败"; }
  finally { saving.value = false; }
}
async function confirmDelete() {
  if (!deleting.value) return;
  deletingBusy.value = true;
  try {
    const response = await apiFetch(`/api/prompts/${deleting.value.id}`, { method: "DELETE" });
    if (!response.ok) throw new Error(message(await readJson(response), "提示词删除失败"));
    deleting.value = null; await loadEntries();
  } catch (exception) { error.value = exception instanceof Error ? exception.message : "提示词删除失败"; }
  finally { deletingBusy.value = false; }
}
function applyEntry(entry: PromptEntry) { emit("apply", entry.prompt, entry.name); }
onMounted(loadEntries);
</script>

<template>
  <section class="prompts-page">
    <header class="prompts-heading"><div><span class="prompts-kicker"><Bookmark :size="14" />个人内容</span><h1>提示词管理</h1><p>保存你反复使用的提示词，随时回到工作台继续创作。</p></div><div class="prompts-heading-actions"><button type="button" class="secondary-action" @click="emit('back')">返回工作台</button><button type="button" class="primary-action" @click="openCreate"><Plus :size="16" />新建提示词</button></div></header>
    <div class="prompts-toolbar"><label class="prompts-search"><Search :size="17" /><input v-model="search" type="search" placeholder="搜索名称或提示词" /></label><select v-model="category" aria-label="筛选提示词分类"><option value="">全部分类</option><option value="__empty__">未分类</option><option v-for="item in categorySuggestions" :key="item" :value="item">{{ item }}</option></select><button type="button" class="secondary-action" @click="loadEntries">刷新</button></div>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
    <div v-if="loading" class="prompts-empty"><LoaderCircle class="spin" :size="22" /><span>正在加载提示词...</span></div>
    <div v-else-if="!visibleEntries.length" class="prompts-empty"><Bookmark :size="25" /><strong>{{ entries.length ? "没有匹配的提示词" : "还没有保存提示词" }}</strong><span>{{ entries.length ? "尝试更换搜索词或分类" : "可以从工作台或这里创建一条可复用提示词。" }}</span></div>
    <div v-else class="prompts-list"><article v-for="entry in visibleEntries" :key="entry.id" class="prompt-entry"><div class="prompt-entry-heading"><div><span class="prompt-entry-category">{{ entry.category || "未分类" }}</span><h2>{{ entry.name }}</h2></div><time>{{ new Date(entry.updated_at).toLocaleDateString('zh-CN') }}</time></div><p>{{ entry.prompt }}</p><div class="prompt-entry-actions"><button type="button" class="primary-action" @click="applyEntry(entry)"><Sparkles :size="15" />应用到工作台</button><button type="button" class="secondary-action" @click="openEdit(entry)"><Edit3 :size="15" />编辑</button><button type="button" class="icon-action danger-action" aria-label="删除提示词" title="删除提示词" @click="deleting = entry"><Trash2 :size="16" /></button></div></article></div>
    <PromptEditorDialog :open="editorOpen" :title="editing ? '编辑提示词' : '保存提示词'" :initial="editing" :category-suggestions="categorySuggestions" @submit="saveEntry" @cancel="editorOpen = false" />
    <ConfirmDialog :open="deleting !== null" title="删除提示词" :message="`确认永久删除“${deleting?.name ?? ''}”吗？删除后无法恢复。`" :busy="deletingBusy" @confirm="confirmDelete" @cancel="deleting = null" />
  </section>
</template>

<style scoped>
.prompts-page { max-width:1100px; min-height:calc(100dvh - 64px); margin:0 auto; padding:32px 48px 56px; }.prompts-heading { display:flex; justify-content:space-between; align-items:flex-end; gap:24px; padding-bottom:22px; border-bottom:1px solid rgba(255,255,255,.14); }.prompts-kicker { display:flex; gap:7px; align-items:center; color:#d8a84e; font-size:11px; letter-spacing:.08em; }.prompts-heading h1 { margin:7px 0 5px; font-size:30px; line-height:1.15; }.prompts-heading p { margin:0; color:#a8adb5; font-size:13px; }.prompts-heading-actions,.prompts-toolbar,.prompt-entry-actions { display:flex; align-items:center; gap:8px; }.prompts-heading-actions .primary-action,.prompts-heading-actions .secondary-action,.prompts-toolbar .secondary-action { min-height:36px; padding-inline:11px; font-size:11px; }.prompts-toolbar { margin:18px 0; }.prompts-search { display:flex; align-items:center; gap:8px; flex:1; max-width:600px; min-height:36px; padding:0 10px; border:1px solid rgba(255,255,255,.18); }.prompts-search input { flex:1; border:0; outline:0; background:transparent; color:inherit; font-size:13px; }.prompts-toolbar select { min-height:36px; padding:8px 10px; border:1px solid rgba(255,255,255,.18); background:#191b1f; color:#f6f4ef; font-size:13px; }.prompts-list { display:grid; gap:10px; }.prompt-entry { padding:16px; border:1px solid rgba(255,255,255,.14); background:rgba(22,24,28,.86); }.prompt-entry-heading { display:flex; justify-content:space-between; gap:12px; }.prompt-entry-heading h2 { margin:5px 0 0; font-size:16px; }.prompt-entry-heading time { color:#8f969f; font-size:11px; }.prompt-entry-category { color:#d8a84e; font-size:11px; }.prompt-entry p { white-space:pre-wrap; margin:10px 0; color:#c1c5ca; font-size:13px; line-height:1.5; max-height:90px; overflow:auto; }.prompt-entry-actions { justify-content:flex-end; flex-wrap:wrap; }.prompt-entry-actions .primary-action,.prompt-entry-actions .secondary-action { min-height:34px; padding-inline:11px; font-size:11px; }.prompt-entry-actions .icon-action { width:34px; height:34px; }.prompts-empty { min-height:260px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:8px; color:#a8adb5; font-size:13px; }.prompts-empty strong { color:#f6f4ef; font-size:15px; }
@media (max-width:760px) { .prompts-page { padding:24px 18px 48px; }.prompts-heading { display:block; }.prompts-heading-actions { margin-top:18px; flex-wrap:wrap; }.prompts-toolbar { flex-wrap:wrap; }.prompts-search { width:100%; max-width:none; } }
</style>
