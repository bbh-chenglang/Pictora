<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Check, Heart, LoaderCircle, Search, Send, Sparkles, Trash2, Upload, X } from "lucide-vue-next";
import fallbackCover from "../assets/genimage-group.png";
import ConfirmDialog from "./ConfirmDialog.vue";

export type SkillWorkflow = {
  prompt_template: string;
  provider_type: "gpt" | "gemini" | "grok";
  model: string;
  quality: string;
  size: string;
  resolution: string;
  image_count: number;
  reference_requirements: Array<"person" | "environment" | "object">;
  multi_view: {
    enabled: boolean;
    target: "person" | "object";
    preset_keys: string[];
    custom_views: Array<{ key: string; label: string }>;
  };
};
type Skill = {
  id: number; author_id: number; author_name: string; title: string; description: string;
  category: "portrait" | "product" | "marketing" | "illustration" | "other";
  status: "draft" | "pending" | "published" | "rejected"; workflow: SkillWorkflow;
  has_cover: boolean; is_favorited: boolean; favorite_count: number; use_count: number;
  moderation_note?: string | null; created_at: string; updated_at: string; published_at?: string | null;
};

const props = defineProps<{
  isAdmin: boolean;
  username: string;
  currentWorkflow: SkillWorkflow;
  coverSource?: string;
}>();
const emit = defineEmits<{
  apply: [workflow: SkillWorkflow, title: string];
  back: [];
}>();

const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const skills = ref<Skill[]>([]);
const tab = ref<"discover" | "mine" | "favorites" | "review">("discover");
const search = ref("");
const category = ref("");
const loading = ref(false);
const error = ref("");
const showCreate = ref(false);
const creating = ref(false);
const createError = ref("");
const title = ref("");
const description = ref("");
const categoryForm = ref<Skill["category"]>("product");
const coverFile = ref<File | null>(null);
const coverPreview = ref("");
const activeSkill = ref<Skill | null>(null);
const reviewNote = ref("");
const reviewingId = ref<number | null>(null);
const actionId = ref<number | null>(null);
const deletingSkill = ref<Skill | null>(null);
const deletingBusy = ref(false);

const categoryLabels: Record<Skill["category"], string> = {
  portrait: "人物",
  product: "商品",
  marketing: "营销",
  illustration: "插画",
  other: "其他",
};
const statusLabels: Record<Skill["status"], string> = {
  draft: "草稿", pending: "审核中", published: "已发布", rejected: "需修改",
};
const tabLabels = computed(() => [
  { id: "discover" as const, label: "发现" },
  { id: "mine" as const, label: "我的技能" },
  { id: "favorites" as const, label: "收藏" },
  ...(props.isAdmin ? [{ id: "review" as const, label: "审核队列" }] : []),
]);

function apiFetch(path: string, init: RequestInit = {}) {
  return fetch(`${API_BASE}${path}`, { ...init, credentials: "include" });
}
async function json(response: Response) {
  try { return await response.json(); } catch { return null; }
}
function errorMessage(data: any, fallback: string) {
  return String(data?.error?.message ?? data?.detail ?? fallback);
}
function coverUrl(skill: Skill) { return skill.has_cover ? `${API_BASE}/api/skills/${skill.id}/cover` : fallbackCover; }
function formatDate(value: string) { return new Date(value).toLocaleDateString("zh-CN", { year: "numeric", month: "numeric", day: "numeric" }); }
function statusClass(skill: Skill) { return `skill-status-${skill.status}`; }

async function loadSkills() {
  loading.value = true; error.value = "";
  try {
    const params = new URLSearchParams({ scope: tab.value });
    if (search.value.trim()) params.set("search", search.value.trim());
    if (category.value) params.set("category", category.value);
    const response = await apiFetch(`/api/skills?${params}`);
    const data = await json(response);
    if (!response.ok) throw new Error(errorMessage(data, "技能加载失败"));
    skills.value = Array.isArray(data) ? data : [];
  } catch (exception) { error.value = exception instanceof Error ? exception.message : "技能加载失败"; }
  finally { loading.value = false; }
}
function selectTab(next: typeof tab.value) { tab.value = next; void loadSkills(); }
function openCreate() {
  title.value = ""; description.value = ""; categoryForm.value = "product"; coverFile.value = null;
  coverPreview.value = props.coverSource ?? ""; createError.value = ""; showCreate.value = true;
}
function closeCreate() { if (!creating.value) showCreate.value = false; }
function handleCover(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] ?? null;
  if (!file) return;
  if (! ["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size > 5 * 1024 * 1024) {
    createError.value = "封面仅支持 JPG、PNG、WebP，且不能超过 5 MB"; return;
  }
  coverFile.value = file; coverPreview.value = URL.createObjectURL(file); createError.value = "";
}
async function createSkill() {
  if (!title.value.trim() || !description.value.trim()) { createError.value = "请填写技能名称和说明"; return; }
  creating.value = true; createError.value = "";
  const form = new FormData();
  form.set("title", title.value.trim()); form.set("description", description.value.trim()); form.set("category", categoryForm.value);
  form.set("workflow_json", JSON.stringify(props.currentWorkflow));
  if (coverFile.value) form.set("cover", coverFile.value);
  else if (coverPreview.value) {
    try {
      const response = await fetch(coverPreview.value, { credentials: "include" });
      if (response.ok) {
        const blob = await response.blob();
        const extension = blob.type === "image/jpeg" ? "jpg" : blob.type === "image/webp" ? "webp" : "png";
        form.set("cover", new File([blob], `skill-cover.${extension}`, { type: blob.type || "image/png" }));
      }
    } catch {
      // A cover is optional; the skill can still be saved with the generated fallback.
    }
  }
  try {
    const response = await apiFetch("/api/skills", { method: "POST", body: form });
    const data = await json(response);
    if (!response.ok) throw new Error(errorMessage(data, "技能创建失败"));
    showCreate.value = false; tab.value = "mine"; await loadSkills();
  } catch (exception) { createError.value = exception instanceof Error ? exception.message : "技能创建失败"; }
  finally { creating.value = false; }
}
async function submitSkill(skill: Skill) {
  actionId.value = skill.id;
  try { const response = await apiFetch(`/api/skills/${skill.id}/submit`, { method: "POST" }); if (!response.ok) throw new Error(errorMessage(await json(response), "提交失败")); await loadSkills(); }
  catch (exception) { error.value = exception instanceof Error ? exception.message : "提交失败"; }
  finally { actionId.value = null; }
}
async function toggleFavorite(skill: Skill) {
  actionId.value = skill.id;
  try {
    const response = await apiFetch(`/api/skills/${skill.id}/favorite`, { method: skill.is_favorited ? "DELETE" : "PUT" });
    if (!response.ok) throw new Error(errorMessage(await json(response), "收藏操作失败"));
    const updated = await json(response); const index = skills.value.findIndex((item) => item.id === skill.id);
    if (index >= 0) skills.value[index] = updated;
  } catch (exception) { error.value = exception instanceof Error ? exception.message : "收藏操作失败"; }
  finally { actionId.value = null; }
}
async function useSkill(skill: Skill) {
  actionId.value = skill.id;
  try {
    const response = await apiFetch(`/api/skills/${skill.id}/use`, { method: "POST" }); const data = await json(response);
    if (!response.ok) throw new Error(errorMessage(data, "技能应用失败"));
    emit("apply", data.workflow, skill.title); activeSkill.value = null;
  } catch (exception) { error.value = exception instanceof Error ? exception.message : "技能应用失败"; }
  finally { actionId.value = null; }
}
async function confirmDeleteSkill() {
  if (!deletingSkill.value) return;
  deletingBusy.value = true;
  try {
    const response = await apiFetch(`/api/skills/${deletingSkill.value.id}`, { method: "DELETE" });
    if (!response.ok) throw new Error(errorMessage(await json(response), "删除失败"));
    deletingSkill.value = null;
    await loadSkills();
  } catch (exception) { error.value = exception instanceof Error ? exception.message : "删除失败"; }
  finally { deletingBusy.value = false; }
}
async function reviewSkill(skill: Skill, decision: "published" | "rejected") {
  reviewingId.value = skill.id;
  try {
    const response = await apiFetch(`/api/skills/${skill.id}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, note: reviewNote.value.trim() }) });
    if (!response.ok) throw new Error(errorMessage(await json(response), "审核失败")); reviewNote.value = ""; await loadSkills();
  } catch (exception) { error.value = exception instanceof Error ? exception.message : "审核失败"; }
  finally { reviewingId.value = null; }
}
onMounted(loadSkills);
</script>

<template>
  <section class="skills-page">
    <header class="skills-heading">
      <div><span class="skills-kicker"><Sparkles :size="14" />社区工作流</span><h1>技能广场</h1><p>把经过验证的生图方法，变成下一次创作的起点。</p></div>
      <div class="skills-heading-actions"><button type="button" class="secondary-action" @click="emit('back')">返回工作台</button><button type="button" class="primary-action" @click="openCreate"><Sparkles :size="16" />从当前配置创建</button></div>
    </header>
    <nav class="skills-tabs" aria-label="技能栏目"><button v-for="item in tabLabels" :key="item.id" type="button" :class="{ active: tab === item.id }" @click="selectTab(item.id)">{{ item.label }}<span v-if="item.id === 'review' && skills.length">{{ skills.length }}</span></button></nav>
    <div class="skills-toolbar"><label class="skills-search"><Search :size="17" /><input v-model="search" type="search" placeholder="搜索技能、场景或作者" @keydown.enter="loadSkills" /></label><select v-model="category" aria-label="筛选技能分类" @change="loadSkills"><option value="">全部分类</option><option v-for="(label, key) in categoryLabels" :key="key" :value="key">{{ label }}</option></select><button type="button" class="secondary-action" @click="loadSkills">刷新</button></div>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
    <div v-if="loading" class="skills-empty"><LoaderCircle class="spin" :size="22" /><span>正在加载技能...</span></div>
    <div v-else-if="!skills.length" class="skills-empty"><Sparkles :size="25" /><strong>{{ tab === 'review' ? '暂无待审核技能' : '还没有找到合适的技能' }}</strong><span>可以从当前工作台配置创建第一个技能。</span></div>
    <div v-else class="skills-grid">
      <article v-for="skill in skills" :key="skill.id" class="skill-card">
        <button type="button" class="skill-cover" @click="activeSkill = skill"><img :src="coverUrl(skill)" :alt="skill.title" /></button>
        <div class="skill-card-body"><div class="skill-card-meta"><span class="skill-category">{{ categoryLabels[skill.category] }}</span><span :class="['skill-status', statusClass(skill)]">{{ statusLabels[skill.status] }}</span></div><h2>{{ skill.title }}</h2><p>{{ skill.description }}</p><div class="skill-card-footer"><span>作者 {{ skill.author_name }}</span><span>{{ skill.use_count }} 次使用</span></div><div class="skill-card-actions"><button v-if="skill.status === 'published' || skill.author_id !== 0" type="button" class="primary-action" :disabled="actionId === skill.id" @click="useSkill(skill)"><LoaderCircle v-if="actionId === skill.id" class="spin" :size="15" /><Sparkles v-else :size="15" />使用此技能</button><button v-if="skill.status === 'published'" type="button" class="icon-action" :class="{ active: skill.is_favorited }" :aria-label="skill.is_favorited ? '取消收藏' : '收藏技能'" :title="skill.is_favorited ? '取消收藏' : '收藏技能'" :disabled="actionId === skill.id" @click="toggleFavorite(skill)"><Heart :size="17" :fill="skill.is_favorited ? 'currentColor' : 'none'" /></button><button v-if="tab === 'mine' && ['draft', 'rejected'].includes(skill.status)" type="button" class="secondary-action" :disabled="actionId === skill.id" @click="submitSkill(skill)"><Send :size="14" />提交审核</button><button v-if="isAdmin || (tab === 'mine' && ['draft', 'rejected'].includes(skill.status))" type="button" class="icon-action danger-action" aria-label="删除技能" title="删除技能" @click="deletingSkill = skill"><Trash2 :size="16" /></button></div><p v-if="skill.moderation_note" class="skill-note">审核意见：{{ skill.moderation_note }}</p></div>
        <div v-if="tab === 'review'" class="skill-review-actions"><input v-model="reviewNote" maxlength="500" placeholder="审核意见（拒绝时建议填写）" /><button type="button" class="secondary-action" :disabled="reviewingId === skill.id" @click="reviewSkill(skill, 'rejected')">拒绝</button><button type="button" class="primary-action" :disabled="reviewingId === skill.id" @click="reviewSkill(skill, 'published')"><Check :size="15" />通过</button></div>
      </article>
    </div>
    <div v-if="activeSkill" class="skill-detail-layer" @click.self="activeSkill = null"><article class="skill-detail"><button type="button" class="icon-action skill-detail-close" aria-label="关闭技能详情" title="关闭" @click="activeSkill = null"><X :size="19" /></button><img :src="coverUrl(activeSkill)" :alt="activeSkill.title" /><div class="skill-detail-copy"><div class="skill-card-meta"><span class="skill-category">{{ categoryLabels[activeSkill.category] }}</span><span>{{ activeSkill.author_name }} · {{ formatDate(activeSkill.updated_at) }}</span></div><h2>{{ activeSkill.title }}</h2><p>{{ activeSkill.description }}</p><dl><div><dt>模型</dt><dd>{{ activeSkill.workflow.model }}</dd></div><div><dt>输出</dt><dd>{{ activeSkill.workflow.image_count }} 张 · {{ activeSkill.workflow.size || activeSkill.workflow.resolution || '自动参数' }}</dd></div><div><dt>参考图</dt><dd>{{ activeSkill.workflow.reference_requirements.length ? activeSkill.workflow.reference_requirements.join('、') : '无需参考图' }}</dd></div></dl><button type="button" class="primary-action" :disabled="actionId === activeSkill.id" @click="useSkill(activeSkill)"><Sparkles :size="16" />应用到工作台</button></div></article></div>
    <div v-if="showCreate" class="skill-create-layer" @click.self="closeCreate"><form class="skill-create-dialog" @submit.prevent="createSkill"><div class="skill-dialog-heading"><div><span>保存当前工作流</span><h2>创建社区 Skill</h2></div><button type="button" class="icon-action" aria-label="关闭" title="关闭" @click="closeCreate"><X :size="19" /></button></div><label>技能名称<input v-model="title" maxlength="80" placeholder="例如：电商商品棚拍" required /></label><label>技能说明<textarea v-model="description" rows="4" maxlength="600" placeholder="说明它解决什么场景、需要什么输入以及会得到什么结果" required></textarea></label><label>分类<select v-model="categoryForm"><option v-for="(label, key) in categoryLabels" :key="key" :value="key">{{ label }}</option></select></label><label>封面图<span class="skill-upload"><input type="file" accept="image/jpeg,image/png,image/webp" @change="handleCover" /><Upload :size="17" /><span>{{ coverFile?.name || '选择一张结果图作为封面' }}</span></span></label><img v-if="coverPreview" class="skill-cover-preview" :src="coverPreview" alt="技能封面预览" /><p class="skill-dialog-hint">发布前需要管理员审核。技能只会保存当前提示词和参数，不会上传你的参考图或 API Key。</p><p v-if="createError" class="error-message" role="alert">{{ createError }}</p><div class="skill-dialog-actions"><button type="button" class="secondary-action" @click="closeCreate">取消</button><button type="submit" class="primary-action" :disabled="creating"><LoaderCircle v-if="creating" class="spin" :size="16" />保存草稿</button></div></form></div>
    <ConfirmDialog :open="deletingSkill !== null" title="删除技能" :message="`确认永久删除“${deletingSkill?.title ?? ''}”吗？删除后无法恢复。`" :busy="deletingBusy" @confirm="confirmDeleteSkill" @cancel="deletingSkill = null" />
  </section>
</template>

<style scoped>
.skills-page { max-width: 1380px; margin: 0 auto; padding: 44px 48px 72px; }
.skills-heading { display:flex; justify-content:space-between; gap:28px; align-items:flex-end; border-bottom:1px solid rgba(255,255,255,.14); padding-bottom:28px; }
.skills-kicker { display:flex; align-items:center; gap:7px; color:#d8a84e; font-size:12px; letter-spacing:.08em; text-transform:uppercase; }
.skills-heading h1 { margin:9px 0 6px; font-size:36px; line-height:1.08; letter-spacing:0; }
.skills-heading p { margin:0; color:#a8adb5; }
.skills-heading-actions,.skill-card-actions,.skills-toolbar { display:flex; align-items:center; gap:10px; }
.skills-tabs { display:flex; gap:22px; border-bottom:1px solid rgba(255,255,255,.1); margin-bottom:20px; }
.skills-tabs button { border:0; background:transparent; color:#8d939c; padding:16px 2px 13px; border-bottom:2px solid transparent; cursor:pointer; }
.skills-tabs button.active { color:#f6f4ef; border-color:#d8a84e; }
.skills-tabs button span { margin-left:6px; color:#d8a84e; }
.skills-toolbar { margin-bottom:26px; }
.skills-search { display:flex; align-items:center; gap:8px; flex:1; max-width:540px; border:1px solid rgba(255,255,255,.18); padding:0 12px; min-height:40px; }
.skills-search input { flex:1; border:0; outline:0; background:transparent; color:inherit; }
.skills-toolbar select,.skill-create-dialog select { border:1px solid rgba(255,255,255,.18); background:#191b1f; color:#f6f4ef; padding:10px 12px; min-height:40px; }
.skills-toolbar select { background:#fff; color:#17191d; border-color:#cfd4dc; }
.skills-toolbar select option { background:#fff; color:#17191d; }
.skills-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:18px; }
.skill-card { background:rgba(22,24,28,.86); border:1px solid rgba(255,255,255,.13); min-width:0; }
.skill-cover { display:block; width:100%; aspect-ratio:4/3; padding:0; border:0; background:#292b31; cursor:pointer; overflow:hidden; }
.skill-cover img { width:100%; height:100%; object-fit:cover; display:block; transition:transform .25s ease; }
.skill-cover:hover img { transform:scale(1.035); }
.skill-card-body { padding:16px; }
.skill-card-meta { display:flex; justify-content:space-between; gap:8px; color:#9ea4ac; font-size:12px; }
.skill-category { color:#d8a84e; }
.skill-status { padding:2px 6px; border:1px solid currentColor; }
.skill-status-published { color:#73c9b5; }.skill-status-pending { color:#d8a84e; }.skill-status-rejected { color:#f28572; }.skill-status-draft { color:#9ea4ac; }
.skill-card h2 { font-size:18px; margin:12px 0 7px; }.skill-card p { color:#aeb3ba; font-size:13px; line-height:1.55; margin:0; min-height:42px; }
.skill-card-footer { display:flex; justify-content:space-between; margin:18px 0 12px; color:#777e87; font-size:12px; }
.skill-card-actions { flex-wrap:wrap; }.skill-card-actions .primary-action { flex:1; justify-content:center; }.skill-card-actions .icon-action.active { color:#ee8171; }
.skill-note { color:#d8a84e !important; border-left:2px solid #d8a84e; padding-left:8px; margin-top:13px !important; min-height:0 !important; }
.skills-empty { min-height:280px; display:flex; flex-direction:column; justify-content:center; align-items:center; gap:11px; color:#a8adb5; }.skills-empty strong { color:#f6f4ef; }
.skill-review-actions { border-top:1px solid rgba(255,255,255,.1); padding:12px 16px; display:flex; gap:8px; }.skill-review-actions input { flex:1; min-width:0; border:1px solid rgba(255,255,255,.16); background:transparent; color:inherit; padding:8px; }
.skill-detail-layer,.skill-create-layer { position:fixed; inset:0; background:rgba(5,6,8,.72); display:grid; place-items:center; z-index:20; padding:24px; }
.skill-detail { width:min(880px,100%); background:#1b1d22; border:1px solid rgba(255,255,255,.18); display:grid; grid-template-columns:minmax(280px,1fr) 1fr; position:relative; }.skill-detail>img { width:100%; height:100%; min-height:370px; object-fit:cover; }.skill-detail-copy { padding:34px; }.skill-detail-copy h2 { font-size:30px; margin:14px 0 10px; }.skill-detail-copy p { color:#b4b8bf; line-height:1.65; }.skill-detail-copy dl { margin:28px 0; display:grid; gap:13px; }.skill-detail-copy dl div { display:flex; justify-content:space-between; gap:20px; border-bottom:1px solid rgba(255,255,255,.1); padding-bottom:9px; }.skill-detail-copy dt { color:#898f98; }.skill-detail-copy dd { margin:0; text-align:right; }.skill-detail-close { position:absolute; right:10px; top:10px; z-index:1; background:rgba(0,0,0,.5); }
.skill-create-dialog { width:min(560px,100%); background:#1b1d22; border:1px solid rgba(255,255,255,.18); padding:28px; display:grid; gap:16px; }.skill-dialog-heading { display:flex; justify-content:space-between; align-items:flex-start; border-bottom:1px solid rgba(255,255,255,.12); padding-bottom:16px; }.skill-dialog-heading span { color:#d8a84e; font-size:12px; }.skill-dialog-heading h2 { margin:5px 0 0; }.skill-create-dialog label { display:grid; gap:7px; color:#d2d4d7; font-size:13px; }.skill-create-dialog input:not([type=file]),.skill-create-dialog textarea { width:100%; box-sizing:border-box; border:1px solid rgba(255,255,255,.17); background:#14161a; color:#f6f4ef; padding:10px; font:inherit; resize:vertical; }.skill-upload { min-height:42px; border:1px dashed rgba(255,255,255,.25); display:flex; gap:8px; align-items:center; padding:0 12px; cursor:pointer; }.skill-upload input { display:none; }.skill-upload span { color:#aeb3ba; }.skill-cover-preview { width:120px; aspect-ratio:4/3; object-fit:cover; }.skill-dialog-hint { color:#8f969f; font-size:12px; line-height:1.5; margin:0; }.skill-dialog-actions { display:flex; justify-content:flex-end; gap:10px; border-top:1px solid rgba(255,255,255,.12); padding-top:16px; }
@media (max-width: 1100px) { .skills-grid { grid-template-columns:repeat(3,minmax(0,1fr)); } }
@media (max-width: 760px) { .skills-page { padding:28px 18px 56px; }.skills-heading { display:block; }.skills-heading-actions { margin-top:22px; flex-wrap:wrap; }.skills-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }.skills-toolbar { flex-wrap:wrap; }.skills-search { max-width:none; width:100%; }.skill-detail { display:block; max-height:calc(100vh - 48px); overflow:auto; }.skill-detail>img { height:230px; min-height:0; }.skill-detail-copy { padding:22px; } }
@media (max-width: 500px) { .skills-grid { grid-template-columns:1fr; }.skill-card p { min-height:0; } }
</style>
